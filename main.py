"""
main entrypoint, CLI commands

Test command:
python3 main.py --dry-run  "/Users/boris/Desktop/Spain instagram photos" -d /Users/boris/Desktop/TestOut


"""

import argparse
import logging
import sys
from pathlib import Path
from scanner import scan_sources


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
        
    # Next steps will be called here
    records = scan_sources(args.sources)
    logging.info(f"Scanner complete. {len(records)} files found.")


if __name__ == "__main__":
    main()