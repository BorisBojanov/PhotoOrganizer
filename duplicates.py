
"""
# duplicates.py
hashing & duplicate detection
"""


import hashlib
import logging
from collections import defaultdict

from config import HASH_ALGORITHM, HASH_CHUNK_SIZE
from models import FileRecord


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


def find_duplicates(records: list[FileRecord]) -> dict[str, list[FileRecord]]:
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

    by_hash = defaultdict(list)
    for record in candidates:
        record.file_hash = compute_hash(record)
        if record.file_hash:
            by_hash[record.file_hash].append(record)

    duplicate_groups = {h: group for h, group in by_hash.items() if len(group) > 1}

    for group in duplicate_groups.values():
        # Keep the first file (sorted by path for deterministic behavior),
        # mark the rest as duplicates pointing at it.
        group.sort(key=lambda r: str(r.path))
        original = group[0]
        for dup in group[1:]:
            dup.is_duplicate = True
            dup.duplicate_of = original.path
            logging.info(f"Duplicate: {dup.path}  ==  {original.path}")

    logging.info(f"Found {len(duplicate_groups)} duplicate groups")
    return duplicate_groups