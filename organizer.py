"""
organizer.py
copy files into year/month folders
"""

# TODO: copied and woud_copy are currenly empty, need to fix that

import os
from pathlib import Path
from pillow_heif import register_heif_opener

import logging
import shutil
import unicodedata
from pathlib import Path
from config import MONTH_NAMES, UNKNOWN_DATE_FOLDER
from models import FileRecord
from datetime import datetime

def build_destination(record: FileRecord, destination_root: Path) -> Path:
    """
    Build the destination path based on the record's date and the destination root.
    """
    if record.date_taken is None:
        folder = destination_root / UNKNOWN_DATE_FOLDER
        new_name = record.path.name
    else:
        dateTaken = record.date_taken
        folder = destination_root / str(dateTaken.year) / MONTH_NAMES[dateTaken.month]
        prefex = dateTaken.strftime("%Y-%m-%d_%H-%M-%S")
        new_name = f"{prefex}_{record.path.name}"
    return folder / new_name

def collision_key(name: str) -> str:
    """
    Normalize a filename for collision checks: case-folded and unicode-
    normalized, so Photo.JPG / photo.jpg (and café.jpg in NFC vs NFD) count
    as the same name on every filesystem — macOS and Linux runs behave
    identically, and the output tree stays safe to move anywhere.
    """
    return unicodedata.normalize("NFC", name).casefold()


def resolve_collision(target: Path, claimed: dict[Path, set[str]]) -> Path:
    """
    Return a target that collides with nothing already on disk NOR anything
    claimed earlier this run, appending _1, _2, ... if needed. `claimed` maps
    each destination folder to the collision_keys taken so far; it is seeded
    from the folder's real contents on first use, and works the same in
    dry-run mode (nothing on disk is required).
    """
    names = claimed.get(target.parent)
    if names is None:
        names = ({collision_key(p.name) for p in target.parent.iterdir()}
                 if target.parent.exists() else set())
        claimed[target.parent] = names

    candidate = target
    counter = 1
    while collision_key(candidate.name) in names:
        candidate = target.with_name(f"{target.stem}_{counter}{target.suffix}")
        counter += 1

    names.add(collision_key(candidate.name))
    return candidate

def is_copyable(r: FileRecord) -> bool:
    """A file gets copied if it exists, is healthy, and isn't a duplicate."""
    return (
        r.exists
        and not r.is_duplicate
        and not r.is_corrupted
        and r.size_bytes > 0
    )


def date_sort_key(r: FileRecord):
    """Sort dated files chronologically; undated files go last."""
    return (r.date_taken is None, r.date_taken or datetime.min)


def sidecar_destination(sidecar_path: Path, media_source: Path, media_target: Path,
                        marker: str = "") -> Path:
    """
    Name a sidecar's destination so it re-pairs with the media file, keeping
    the convention the sidecar used at the source: appended names
    (IMG_1234.JPG.xmp → IMG_1234.JPG.xmp tail kept) vs replaced-extension
    names (IMG_1234.xmp → media extension swapped for the sidecar's).
    """
    if sidecar_path.name.startswith(media_source.name):
        tail = sidecar_path.name[len(media_source.name):]
        target_name = media_target.name + marker + tail
    else:
        target_name = media_target.stem + marker + sidecar_path.suffix
    return media_target.with_name(target_name)


def copy_sidecar(sidecar_path: Path, media_source: Path, media_target: Path,
                 claimed: dict[Path, set[str]], marker: str = "",
                 dry_run: bool = False) -> Path:
    """Copy a sidecar next to its media file's destination."""
    sidecar_target = resolve_collision(
        sidecar_destination(sidecar_path, media_source, media_target, marker),
        claimed,
    )
    if not dry_run:
        shutil.copy2(sidecar_path, sidecar_target)
    return sidecar_target


def organize(records: list[FileRecord], destination_root: Path, dry_run: bool = False):
    """
    Organize files based on their date taken.
    """
    copied = 0
    skipped_dup = 0
    skipped_bad = 0

    
    # to_copy = sorted(
    #     (r for r in records if r.exists and not r.is_duplicate
    #      and not r.is_corrupted and r.size_bytes > 0),
    #     key=lambda r: (r.date_taken is None, r.date_taken or 0)
    #     )
    to_copy = sorted(filter(is_copyable, records), key=date_sort_key)

    skipped_dup = sum(1 for r in records if r.is_duplicate)
    skipped_bad = sum(1 for r in records
        if not r.exists or r.is_corrupted or r.size_bytes == 0
    )

    would_copy = 0
    sidecars = 0
    claimed: dict[Path, set[str]] = {}  # collision registry for this run
    for record in to_copy:
        target_path = build_destination(record, destination_root)
        final_target = resolve_collision(target_path, claimed)
        record.destination = final_target  # Store the destination path in the record

        if dry_run:
            would_copy += 1
            logging.info(f"DRY RUN: Would copy {record.path} to {final_target}")
            if record.sidecar_path:
                sidecar_target = copy_sidecar(
                    record.sidecar_path, record.path, final_target,
                    claimed, dry_run=True,
                )
                sidecars += 1
                logging.info(
                    f"DRY RUN: Would copy sidecar {record.sidecar_path} "
                    f"to {sidecar_target}"
                )
            continue

        final_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(record.path, final_target) # copy2 preserves timestamps
        record.was_copied = True  # Mark the record as copied
        copied += 1
        logging.info(f"Copied {record.path} to {final_target}")

        if record.sidecar_path:
            sidecar_target = copy_sidecar(
                record.sidecar_path, record.path, final_target, claimed
            )
            sidecars += 1
            logging.info(f"Copied sidecar {record.sidecar_path} to {sidecar_target}")

    # Duplicates aren't copied, but their sidecars may hold context the kept
    # copy's sidecar doesn't (e.g. a different Takeout album), so park them
    # next to the kept copy with a .dupN marker.
    dest_by_source = {r.path: r.destination for r in to_copy if r.destination}
    dup_sidecar_counts = {}
    dup_sidecars = 0
    for record in records:
        if not (record.is_duplicate and record.sidecar_path and record.duplicate_of):
            continue
        kept_destination = dest_by_source.get(record.duplicate_of)
        if kept_destination is None:
            continue
        n = dup_sidecar_counts.get(record.duplicate_of, 0) + 1
        dup_sidecar_counts[record.duplicate_of] = n

        sidecar_target = copy_sidecar(
            record.sidecar_path, record.path, kept_destination,
            claimed, marker=f".dup{n}", dry_run=dry_run,
        )
        dup_sidecars += 1
        if dry_run:
            logging.info(
                f"DRY RUN: Would copy duplicate's sidecar {record.sidecar_path} "
                f"to {sidecar_target}"
            )
        else:
            logging.info(
                f"Copied duplicate's sidecar {record.sidecar_path} to {sidecar_target}"
            )

    if dry_run:
        logging.info(
            f"Organize complete (DRY RUN). Would copy: {would_copy}, "
            f"sidecars: {sidecars}, "
            f"skipped duplicates: {skipped_dup}, skipped problematic: {skipped_bad}, "
            f"duplicate sidecars preserved: {dup_sidecars}"
        )
    else:
        logging.info(
            f"Organize complete. Copied: {copied}, "
            f"sidecars: {sidecars}, "
            f"skipped duplicates: {skipped_dup}, skipped problematic: {skipped_bad}, "
            f"duplicate sidecars preserved: {dup_sidecars}"
        )
