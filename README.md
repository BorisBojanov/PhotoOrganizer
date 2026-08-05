# PhotoOrganizer

Organizes a messy photo/video collection (e.g. a Google Takeout export) into a
clean `Year / Month` folder tree, sorted by the date each photo was actually
taken. Files are **copied, never moved or deleted** — the source stays intact.

```text
TestOut/
├── 2020/
│   └── 07 July/
│       ├── 2020-07-05_22-23-28_IMG_1234.jpg
│       ├── 2020-07-05_22-23-28_IMG_1234.jpg.supplemental-metadata.json
│       └── ...
├── Unknown Date/
└── report_2026-08-04_170819.csv
```

## Usage

```bash
python main.py SOURCE_DIR [SOURCE_DIR ...] -d DESTINATION_DIR [--dry-run] [--log-file PATH] [--deep-verify] [--no-ffprobe] [--workers N]
```

- `sources` — one or more directories to scan (recursively).
- `--destination / -d` — root folder for the organized tree (required).
- `--dry-run` — log everything the run *would* do without copying a single file.
  Always do this first; the summary and CSV report are produced either way.
- `--log-file` — log destination (default `photo_organizer.log`).
- `--deep-verify` — fully decode every image's pixels during the integrity
  check. Catches truncation past the header, but takes hours on large
  libraries; the default only validates file structure.
- `--no-ffprobe` — run without ffprobe (video dates fall back to
  sidecar/filename, video integrity is not checked). Without this flag, a
  missing ffprobe aborts the run at startup instead of degrading silently.
- `--workers` — thread count for the metadata, integrity, and hashing phases
  (default: CPU count, capped at 8).

Example:

```bash
python main.py --dry-run ~/Desktop/TestInput -d ~/Desktop/TestOut
```

## Setup

Requires **Python 3.10+** and [ffmpeg](https://ffmpeg.org) (`ffprobe` is used
for video metadata and corruption checks). If `ffprobe` is not on PATH the
run aborts at startup with instructions; pass `--no-ffprobe` to proceed
without video checks.

### macOS / Linux

```bash
python3 -m venv .photoOrganize
./.photoOrganize/bin/pip install -r requirements.txt
brew install ffmpeg          # macOS
sudo apt install ffmpeg      # Debian / Ubuntu / Raspberry Pi OS
```

Then run with the venv's interpreter: `./.photoOrganize/bin/python main.py ...`

### Windows

1. **Install Python 3.10+** from [python.org](https://www.python.org/downloads/)
   or the Microsoft Store. On the python.org installer, tick
   *"Add python.exe to PATH"*.

2. **Create the venv and install dependencies** (PowerShell or cmd, from the
   project folder):

   ```powershell
   py -m venv .photoOrganize
   .photoOrganize\Scripts\pip install -r requirements.txt
   ```

3. **Install ffmpeg** so `ffprobe` is on your PATH:

   ```powershell
   winget install Gyan.FFmpeg
   ```

   (or download a build from [ffmpeg.org](https://ffmpeg.org/download.html),
   unzip it, and add its `bin` folder to PATH). Open a **new** terminal
   afterwards and confirm with `ffprobe -version`.

4. **Run** with the venv's interpreter — note `Scripts\` instead of `bin/`,
   and backslashes in paths:

   ```powershell
   .photoOrganize\Scripts\python main.py --dry-run C:\Users\you\Pictures\TestInput -d D:\Organized
   ```

Windows notes:

- **Long paths**: Windows historically limits paths to 260 characters, and the
  date prefix makes names longer. If you see `FileNotFoundError` on deep
  folders, either keep the destination near a drive root (e.g. `D:\Organized`)
  or enable long paths once in an *administrator* PowerShell:

  ```powershell
  Set-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1
  ```

- **Case handling**: NTFS is case-insensitive like macOS; collision detection
  is case-insensitive by policy anyway, so the output tree is identical across
  Windows, macOS, and Linux.
- Filenames are safe as-is — the `2020-07-05_22-23-28_` prefix uses no
  characters that are illegal on Windows.

## How it works

The pipeline in `main.py` runs five stages, each filling in more of a shared
`FileRecord` per file ([models.py](models.py)):

1. **Scan** ([scanner.py](scanner.py)) — walk the source trees, keep supported
   extensions (jpg/jpeg/heic/png/tiff/webp, mp4/mov/m4v/avi/mkv), check
   existence, readability, and size.
2. **Metadata** ([metadata.py](metadata.py)) — determine `date_taken` using the
   first source that answers, in order of trustworthiness:
   EXIF (images) / ffprobe creation time (videos) → sidecar JSON
   (`photoTakenTime`) → date parsed from the filename → file modified time.
   The winning source is recorded per file. Camera make/model and GPS are
   captured when available. Sidecar files are located here too (see below).
3. **Integrity** ([integrity.py](integrity.py)) — validate each image's file
   structure (Pillow `verify()`; add `--deep-verify` to also decode every
   pixel) and parse each video's stream structure (ffprobe). Corrupted files
   are excluded from copying and flagged in the report. An ffprobe timeout or
   warning is recorded in the file's `errors` column, not treated as
   corruption.
4. **Duplicates** ([duplicates.py](duplicates.py)) — group by file size, then
   SHA-256 the candidates. Every file in a group is byte-identical, so the
   copy that is kept is the *best documented* one: the most trustworthy date
   source wins, then having a sidecar, then GPS, then a name without a
   `(1)` copy-suffix, then the shallowest path. The rest are marked as
   duplicates and not copied.
5. **Organize** ([organizer.py](organizer.py)) — copy the survivors into
   `YEAR/MM Month/` with a `YYYY-MM-DD_HH-MM-SS_` prefix on the original name
   (undated files go to `Unknown Date/` unrenamed). Name collisions get a
   `_1`, `_2`, … counter — nothing is ever overwritten. Collisions are
   detected case-insensitively (and unicode-normalized) regardless of the
   filesystem, so a run produces the same tree on macOS and Linux, and the
   output stays safe to copy onto any drive. `shutil.copy2` preserves file
   timestamps.

Afterwards [reporter.py](reporter.py) writes two CSVs into the destination:

- `report_<timestamp>.csv` — one row per file: status (`copied` /
  `duplicate` / `corrupted` / …), the date and which source provided it,
  camera, GPS, hash, destination, and any errors.
- `duplicates_<timestamp>.csv` — one row per file in each duplicate set,
  grouped and sorted with the biggest space savings first. `role` marks the
  `kept` copy vs the `duplicate`s, and `reclaimed_bytes` is filled in on the
  kept row only, so summing that column gives the true total saved.

### Progress and ETA

The metadata, integrity, and hashing stages run in a thread pool and report
progress through [progress.py](progress.py):

```
Integrity: 8420/32705 (25.7%) | 71.2 GB of 310.4 GB | 44.1 files/s | elapsed 3m 12s | ETA 9m 18s
```

The ETA is computed from **bytes** finished rather than files finished — these
stages are I/O bound, and a 4 GB video is not "one file" worth of work next to
a 2 MB jpg. Lines are throttled to one every 15 seconds, so a multi-hour run
produces a readable trickle instead of 32,705 lines.

## Sidecar files

Sidecars (Google Takeout `*.supplemental-metadata.json`, Lightroom/darktable
`*.xmp`) often hold data that isn't extracted yet — albums, descriptions,
people tags — so the organizer preserves them all; you can always delete them
later, but you can't un-lose them.

- Every copied file's sidecar is copied next to it, renamed to keep the pair
  matched (`2020-07-05_..._IMG_1234.jpg.supplemental-metadata.json`). Both
  pairing conventions are preserved: appended (`IMG_1234.JPG.xmp`) and
  replaced-extension (`IMG_1234.xmp`).
- A skipped duplicate's sidecar may still be unique (the same Takeout photo in
  two albums has two different JSONs), so it is copied next to the kept copy
  with a `.dupN` marker: `..._IMG_1234.jpg.dup1.supplemental-metadata.json`.
- Truncated Google sidecar names are matched by prefix, and sidecar name
  collisions get the same `_N` counter as media files.
