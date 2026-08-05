
"""
# duplicates.py
hashing & duplicate detection
"""


import hashlib
import logging
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from config import HASH_ALGORITHM, HASH_CHUNK_SIZE
from models import FileRecord
from progress import Progress, format_bytes

# How much we trust each date source, best first. Used to pick which copy of
# a duplicate set to keep.
DATE_SOURCE_RANK = {
    "exif": 0,
    "video_container": 1,
    "sidecar": 2,
    "filename": 3,
    "file_modified": 4,
}

# Google Takeout / Windows style copy suffix: "IMG_1234(1).jpg"
COPY_SUFFIX = re.compile(r"\(\d+\)$")


def compute_hash(record: FileRecord) -> str:
    """
    Hash a file's content in chunks so a 4 GB video
    never gets loaded into RAM all at once.
    """
    hasher = hashlib.new(HASH_ALGORITHM)
    try:
        with open(record.path, "rb") as f:
            while chunk := f.read(HASH_CHUNK_SIZE):
                hasher.update(chunk)
        return hasher.hexdigest()
    except OSError as e:
        record.errors.append(f"Hashing failed: {e}")
        return ""


def keeper_rank(record: FileRecord) -> tuple:
    """
    Sort key deciding which copy of an identical set to keep — lower wins.

    Every file in the group is byte-identical, so the pixels are not in
    question; what differs is how much we know *about* each copy. Keep the
    one with the most trustworthy date, a sidecar, and a clean name, so the
    kept file lands in the right month folder instead of under whatever
    date the worst copy happened to carry.
    """
    return (
        DATE_SOURCE_RANK.get(record.data_source, 9),  # best date wins
        not record.has_sidecar,                       # False(0) sorts first
        record.gps_lat is None,                       # geotagged wins
        bool(COPY_SUFFIX.search(record.path.stem)),   # "photo(1).jpg" loses
        len(record.path.parts),                       # shallower path wins
        str(record.path),                             # deterministic tiebreak
    )


def summarize_duplicates(groups: dict[str, list[FileRecord]]) -> dict:
    """Roll duplicate groups up into the numbers worth printing."""
    redundant = [r for group in groups.values() for r in group if r.is_duplicate]
    wasted = sum(r.size_bytes for r in redundant)

    # The groups costing the most space — worth eyeballing before a real run.
    biggest = sorted(
        groups.values(),
        key=lambda g: sum(r.size_bytes for r in g if r.is_duplicate),
        reverse=True,
    )[:5]

    return {
        "groups": len(groups),
        "redundant_files": len(redundant),
        "wasted_bytes": wasted,
        "biggest_groups": biggest,
    }


def log_duplicate_summary(groups: dict[str, list[FileRecord]]) -> dict:
    """Print the duplicate findings as a short, readable block."""
    stats = summarize_duplicates(groups)
    if not stats["groups"]:
        logging.info("Duplicates: none found.")
        return stats

    logging.info(
        f"Duplicates: {stats['groups']} groups, "
        f"{stats['redundant_files']} redundant copies, "
        f"{format_bytes(stats['wasted_bytes'])} not copied"
    )
    for group in stats["biggest_groups"]:
        kept = next((r for r in group if not r.is_duplicate), group[0])
        dup_bytes = sum(r.size_bytes for r in group if r.is_duplicate)
        logging.info(
            f"  {format_bytes(dup_bytes)} saved — {len(group)} copies of "
            f"{kept.path.name} (keeping {kept.path})"
        )
    return stats


def find_duplicates(records: list[FileRecord],
                    workers: int = 8) -> dict[str, list[FileRecord]]:
    """
    Hash all healthy files and group them by hash.
    Returns only the groups that contain 2+ files (actual duplicates).
    Marks all but the first file in each group as duplicates.
    """
    # Optimization: files with different sizes CANNOT be identical.
    # Group by size first, only hash files that share a size with another.
    by_size = defaultdict(list)
    for r in records:
        if r.exists and r.size_bytes > 0 and not r.is_corrupted:
            by_size[r.size_bytes].append(r)

    candidates = [r for group in by_size.values() if len(group) > 1 for r in group]
    logging.info(f"{len(candidates)} files share a size with another — hashing those")

    # Hashing reads every byte, so bytes — not file count — are the honest
    # measure of how far along we are.
    progress = Progress("Hashing", len(candidates),
                        total_bytes=sum(r.size_bytes for r in candidates))

    def _hash(record: FileRecord) -> None:
        try:
            record.file_hash = compute_hash(record)
        finally:
            progress.advance(record.size_bytes)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(_hash, candidates))
    progress.finish()

    by_hash = defaultdict(list)
    for record in candidates:
        if record.file_hash:
            by_hash[record.file_hash].append(record)

    duplicate_groups = {h: group for h, group in by_hash.items() if len(group) > 1}

    for group in duplicate_groups.values():
        # Keep the best-documented copy, mark the rest as duplicates of it.
        group.sort(key=keeper_rank)
        original = group[0]
        for dup in group[1:]:
            dup.is_duplicate = True
            dup.duplicate_of = original.path
            logging.debug(f"Duplicate: {dup.path}  ==  {original.path}")

    logging.info(f"Found {len(duplicate_groups)} duplicate groups")
    return duplicate_groups