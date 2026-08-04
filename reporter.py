"""
reporter.py
generate final report

creates a summary of everything the run did.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path

from models import FileRecord


def write_report(records: list[FileRecord], dest_root: Path, dry_run: bool) -> Path:
    """Write a CSV with one row per file — the permanent record of the run."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    suffix = "_dryrun" if dry_run else ""
    report_path = dest_root / f"report_{timestamp}{suffix}.csv"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "source_path", "status", "date_taken", "date_source",
        "camera_make", "camera_model", "gps_lat", "gps_lon",
        "size_bytes", "file_hash", "duplicate_of",
        "corrupted_reason", "destination", "errors",
    ]

    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow({
                "source_path": str(r.path),
                "status": _status(r, dry_run),
                "date_taken": r.date_taken.isoformat() if r.date_taken else "",
                "date_source": r.data_source,
                "camera_make": r.camera_make,
                "camera_model": r.camera_model,
                "gps_lat": r.gps_lat if r.gps_lat is not None else "",
                "gps_lon": r.gps_lon if r.gps_lon is not None else "",
                "size_bytes": r.size_bytes,
                "file_hash": r.file_hash,
                "duplicate_of": str(r.duplicate_of) if r.duplicate_of else "",
                "corrupted_reason": r.corrupted_reason,
                "destination": str(r.destination) if r.destination else "",
                "errors": "; ".join(r.errors),
            })

    logging.info(f"Report written: {report_path}")
    return report_path


def _status(r: FileRecord, dry_run: bool) -> str:
    """One clear word per file — makes the CSV filterable at a glance."""
    if not r.exists:
        return "missing"
    if r.size_bytes == 0:
        return "empty"
    if r.is_corrupted:
        return "corrupted"
    if r.is_duplicate:
        return "duplicate"
    if r.was_copied:
        return "copied"
    if dry_run and r.destination:
        return "would_copy"
    return "not_copied"