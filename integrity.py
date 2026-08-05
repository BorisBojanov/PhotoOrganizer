"""
detect corrupted files
A file can exist, be readable, have a plausible size, 
    even have EXIF — and still be un-decodable garbage past the header (classic partial-copy damage). 
The only true test is decoding the actual pixel data
"""

# integrity.py

import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from config import VIDEO_EXTENSIONS
from models import FileRecord
from progress import Progress

FFPROBE_TIMEOUT_S = 30


def check_image(record: FileRecord, deep: bool = False) -> None:
    try:
        with Image.open(record.path) as img:
            img.verify()          # cheap structural check
        if deep:
            # verify() invalidates the object — must reopen to decode pixels
            with Image.open(record.path) as img:
                img.load()        # full decode; catches truncated files
    except Exception as e:
        record.is_corrupted = True
        record.corrupted_reason = str(e)


def check_video(record: FileRecord) -> None:
    """If ffprobe can't parse the stream structure, the file is damaged."""
    cmd = ["ffprobe", "-v", "error", "-show_entries",
           "stream=codec_type", str(record.path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=FFPROBE_TIMEOUT_S)
    except FileNotFoundError:
        # ffprobe missing is a setup problem, not file damage
        record.errors.append("ffprobe not found — video integrity not checked")
        return
    except subprocess.TimeoutExpired:
        # slow disk or unsynced cloud placeholder, not proven damage
        record.errors.append(
            f"ffprobe timed out after {FFPROBE_TIMEOUT_S}s — integrity not checked")
        return
    except Exception as e:
        record.errors.append(f"ffprobe failed to run: {e}")
        return

    if result.returncode != 0:
        record.is_corrupted = True
        record.corrupted_reason = result.stderr.strip()[:200] or "ffprobe failed"
    elif result.stderr.strip():
        # warnings on stderr with exit code 0 are not corruption
        record.errors.append(f"ffprobe warning: {result.stderr.strip()[:200]}")


def check_integrity(records: list[FileRecord], deep_verify: bool = False,
                    workers: int = 8) -> int:
    # Build this phase's own worklist first. The scanner's "total files"
    # counts everything found; missing and empty files are skipped here, so
    # using that number as the ETA denominator would stall the bar at 99%.
    todo = [r for r in records if r.exists and r.size_bytes > 0]
    progress = Progress("Integrity", len(todo),
                        total_bytes=sum(r.size_bytes for r in todo))

    def _check(record: FileRecord) -> None:
        try:
            if record.path.suffix.lower() in VIDEO_EXTENSIONS:
                check_video(record)
            else:
                check_image(record, deep=deep_verify)
            if record.is_corrupted:
                logging.warning(f"Corrupted: {record.path} — {record.corrupted_reason}")
        finally:
            # finally: a crash in one file must not freeze the ETA
            progress.advance(record.size_bytes)

    mode = "deep (full pixel decode)" if deep_verify else "fast (structure only)"
    logging.info(f"Integrity check: {mode}, {workers} workers, "
                 f"{len(todo)} files to check")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_check, todo))
    progress.finish()

    corrupted = sum(1 for r in records if r.is_corrupted)
    logging.info(f"Integrity check complete. {corrupted} corrupted files.")
    return corrupted