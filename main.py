"""
main entrypoint, CLI commands

Test command:
python3 main.py --dry-run "/Users/boris/Desktop/TestInput" -d "/Users/boris/Desktop/TestOut"


"""

import argparse
import logging
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def setup_logging(log_file: Path) -> None: # type hint Path, and -> None is A return type hint
    """"Create logs to both the consol and a file"""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Organize photos and videos by date taken."
    )
    parser.add_argument(
        "sources",
        nargs="+",                  # one or more source dirs
        type=Path,
        help="One or more source directories to scan.",
    )
    parser.add_argument(
        "--destination", "-d",
        type=Path,
        required=True,
        help="Destination directory for organized files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the run without copying any files.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("photo_organizer.log"),
        help="Path to the log file (default: photo_organizer.log).",
    )
    parser.add_argument(
        "--deep-verify",
        action="store_true",
        help="Fully decode every image's pixel data during the integrity "
             "check. Catches truncation past the header, but is much slower; "
             "the default only validates file structure.",
    )
    parser.add_argument(
        "--no-ffprobe",
        action="store_true",
        help="Run without ffprobe: video dates fall back to sidecar/filename "
             "and video integrity is not checked.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(8, os.cpu_count() or 4),
        help="Thread count for metadata, integrity, and hashing phases "
             "(default: %(default)s).",
    )
    return parser.parse_args()

def validate_args(args: argparse.Namespace) -> bool:
    """Check that sourse directory exists before doing any work."""
    valid:bool = True
    for source in args.sources:
        if (not source.exists()): 
            logging.error(f"Sourse directory does not exist: {source}")
            valid = False
        elif (not source.is_dir()):
            logging.error(f"Sourse is not a directory: {source}")
            valid = False
    return valid
    
def main():
    args = parse_args()
    setup_logging(args.log_file)

    logging.info("=== Starting photo organizer ===")
    if args.dry_run:
        logging.info("DRY RUN mode - no files will be copied or modified.")

    if not validate_args(args):
        sys.exit(1)

    else:
        logging.info(f"Sources: {[str(s) for s in args.sources]}")
        logging.info(f"Destination: {args.destination}")

    # Fail fast on a broken setup: without ffprobe every video would silently
    # lose its container date and skip its integrity check.
    if shutil.which("ffprobe") is None and not args.no_ffprobe:
        logging.error(
            "ffprobe not found on PATH. It is required for video dates and "
            "video integrity checks — install ffmpeg (Windows: winget install "
            "Gyan.FFmpeg, then open a NEW terminal). To run without video "
            "checks anyway, pass --no-ffprobe."
        )
        sys.exit(1)

    # Next steps will be called here
    from scanner import scan_sources

    records = scan_sources(args.sources)
    # logging.info(f"Scanner complete. {len(records)} files found.")

    #Metadata loop
    from metadata import enrich_metadata

    logging.info(f"Reading metadata ({args.workers} workers)...")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(enrich_metadata, records))
    # Quick sanity check log:
    sources = {}

    # Integrity check loop
    # logging.info("Checking file integrity...")
    from integrity import check_integrity

    check_integrity(records, deep_verify=args.deep_verify, workers=args.workers)

    # Douplicate detection loop
    # after the metadata loop and integrity check
    for r in records:
        sources[r.data_source] = sources.get(r.data_source, 0) + 1
    # logging.info(f"Data sources: {sources}")
    # logging.info("Checking for duplicates...")
    from duplicates import find_duplicates

    duplicate_groups = find_duplicates(records, workers=args.workers)

    # organize files based on their date taken
    # logging.info("Organizing files...")
    from organizer import organize

    organize(records, args.destination, args.dry_run)

    from reporter import write_report

    write_report(records, args.destination, args.dry_run)



if __name__ == "__main__":
    main()