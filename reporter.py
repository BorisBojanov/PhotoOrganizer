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


def write_duplicates_report(groups: dict[str, list[FileRecord]], dest_root: Path,
                            dry_run: bool) -> Path | None:
    """
    Write one row per file in every duplicate set, grouped together.

    The main report has a row per file and answers "what happened to this
    file?". This one answers "what am I about to drop, and what is it a
    copy of?" — sorted so the space hogs are at the top, which is the order
    you want when auditing a dry run before committing to it.
    """
    if not groups:
        return None

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    suffix = "_dryrun" if dry_run else ""
    report_path = dest_root / f"duplicates_{timestamp}{suffix}.csv"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    ordered = sorted(
        groups.values(),
        key=lambda g: sum(r.size_bytes for r in g if r.is_duplicate),
        reverse=True,
    )

    fields = ["group", "role", "path", "size_bytes", "date_taken",
              "date_source", "has_sidecar", "reclaimed_bytes", "file_hash"]

    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for index, group in enumerate(ordered, start=1):
            reclaimed = sum(r.size_bytes for r in group if r.is_duplicate)
            for r in group:
                writer.writerow({
                    "group": index,
                    "role": "duplicate" if r.is_duplicate else "kept",
                    "path": str(r.path),
                    "size_bytes": r.size_bytes,
                    "date_taken": r.date_taken.isoformat() if r.date_taken else "",
                    "date_source": r.data_source,
                    "has_sidecar": r.has_sidecar,
                    # written on the group's kept row only, so summing the
                    # column gives the true total instead of double counting
                    "reclaimed_bytes": "" if r.is_duplicate else reclaimed,
                    "file_hash": r.file_hash,
                })

    logging.info(f"Duplicates report written: {report_path}")
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