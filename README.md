# PhotoOrganizer

Organizes a messy photo/video collection (e.g. a Google Takeout export) into a
clean `Year / Month` folder tree, sorted by the date each photo was actually
taken. Files are **copied, never moved or deleted** — the source stays intact.

```
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
python main.py SOURCE_DIR [SOURCE_DIR ...] -d DESTINATION_DIR [--dry-run] [--log-file PATH]
```

- `sources` — one or more directories to scan (recursively).
- `--destination / -d` — root folder for the organized tree (required).
- `--dry-run` — log everything the run *would* do without copying a single file.
  Always do this first; the summary and CSV report are produced either way.
- `--log-file` — log destination (default `photo_organizer.log`).

Example:

```bash
python main.py --dry-run ~/Desktop/TestInput -d ~/Desktop/TestOut
```

## Setup

Requires **Python 3.10+** and [ffmpeg](https://ffmpeg.org) (`ffprobe` is used
for video metadata and corruption checks; without it videos fall back to other
date sources and skip the integrity check).

```bash
python3 -m venv .photoOrganize
./.photoOrganize/bin/pip install -r requirements.txt
brew install ffmpeg   # macOS
```

Then run with the venv's interpreter: `./.photoOrganize/bin/python main.py ...`

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
3. **Integrity** ([integrity.py](integrity.py)) — fully decode each image
   (Pillow) and parse each video's stream structure (ffprobe). Corrupted files
   are excluded from copying and flagged in the report.
4. **Duplicates** ([duplicates.py](duplicates.py)) — group by file size, then
   SHA-256 the candidates. In each identical group the first path (sorted) is
   kept; the rest are marked as duplicates and not copied.
5. **Organize** ([organizer.py](organizer.py)) — copy the survivors into
   `YEAR/MM Month/` with a `YYYY-MM-DD_HH-MM-SS_` prefix on the original name
   (undated files go to `Unknown Date/` unrenamed). Name collisions get a
   `_1`, `_2`, … counter — nothing is ever overwritten. `shutil.copy2`
   preserves file timestamps.

Afterwards [reporter.py](reporter.py) writes a CSV into the destination with
one row per file: status (`copied` / `duplicate` / `corrupted` / …), the date
and which source provided it, camera, GPS, hash, destination, and any errors.

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
