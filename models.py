from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Optional


@dataclass
class FileRecord:
    path: Path
    exists: bool = False
    size_bytes: int = 0

    # Medadata
    date_taken: Optional[datetime] = None
    data_source: str = ""
    camera_make: str = ""
    camera_model: str = ""
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    # gps_alt: Optional[float] = None # Not all have this


    # Integrity
    is_corrupted: bool = False
    corrupted_reason: str = ""

    # Douplicate detection
    file_hash: str = ""
    is_duplicate: bool = False
    duplicate_of: Optional[Path] = None # Path of the file that we are keeping

    # Output
    destination: Optional[Path] = None
    was_copied: bool = False

    # Errors encountered during processing
    errors: list = field(default_factory=list)
    