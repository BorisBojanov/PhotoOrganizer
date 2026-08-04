"""
detect corrupted files
A file can exist, be readable, have a plausible size, 
    even have EXIF — and still be un-decodable garbage past the header (classic partial-copy damage). 
The only true test is decoding the actual pixel data
"""

# integrity.py

import logging
import subprocess

from PIL import Image

from config import VIDEO_EXTENSIONS
from models import FileRecord


def check_image(record: FileRecord) -> None:
    try:
        with Image.open(record.path) as img:
            img.verify()          # cheap structural check
        # verify() invalidates the object — must reopen to decode pixels
        with Image.open(record.path) as img:
            img.load()            # full decode; catches truncated files
    except Exception as e:
        record.is_corrupted = True
        record.corrupted_reason = str(e)


def check_video(record: FileRecord) -> None:
    """If ffprobe can't parse the stream structure, the file is damaged."""
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries",
               "stream=codec_type", str(record.path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0 or result.stderr.strip():
            record.is_corrupted = True
            record.corrupted_reason = result.stderr.strip()[:200] or "ffprobe failed"
    except Exception as e:
        record.is_corrupted = True
        record.corrupted_reason = str(e)


def check_integrity(records: list[FileRecord]) -> int:
    corrupted = 0
    for record in records:
        if not record.exists or record.size_bytes == 0:
            continue
        if record.path.suffix.lower() in VIDEO_EXTENSIONS:
            check_video(record)
        else:
            check_image(record)
        if record.is_corrupted:
            corrupted += 1
            logging.warning(f"Corrupted: {record.path} — {record.corrupted_reason}")
    logging.info(f"Integrity check complete. {corrupted} corrupted files.")
    return corrupted