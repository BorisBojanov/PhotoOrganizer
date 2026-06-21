"""
file discovery & existence check
find files in a directory and subdirectories, checks if the files exists
"""

import logging
import os
import sys
from pathlib import Path
from typing import Generator #add static type hints to generator functions

from config import ALL_SUPPORTED_EXTENSIONS
from models import FileRecord

def is_supported(path:Path) -> bool:
    """return true when the file's extension is supported"""
    return path.suffix.lower() in ALL_SUPPORTED_EXTENSIONS #returns bool

def check_file(path:Path) -> FileRecord:
    """
    Creates a FileRecord object for a single file and fills in the info fields.
    Checking if the files exists, readability, and size
    """
    record = FileRecord(path=path)

    if (not path.exists()):
        record.exists = False
        record.errors.append("File does not exist.")
        return record

    if (not os.access(path, os.R_OK)):
        record.exists = True
        record.errors.append("File is real but no read permissions.")
        return record
    
    # If we are here, the file exists and is readable
    stat = path.stat()
    record.exists = True
    record.size_bytes = stat.st_size

    # Check if the file is empty
    if stat.st_size == 0:
        record.errors.append("File is empty.")
    
    # We could add more checks here, 
    # like checking if the file is corrupted, 
    # would require trying to open the file 
    #   and read its metadata, which is more complex and time-consuming. For now, we will just check for existence and readability.
    return record

def scan_sources(source_dirs: list[Path]) -> list[FileRecord]:
    """
    Walk through directories and find all supported files, 
    return a list of FileRecord objects with the initial-info~(without opening and reading the whole file) filled in.
    """
    
    records: list[FileRecord] = [] #empty list first
    seen_paths: set[Path] = set() # to make sure we don't add the same file twice.

    for source in source_dirs:
        logging.info(f"Scanning: {source}")
        file_count = 0

        for path in source.rglob("*"): ## rglob("*") goes through all files and subdirectories
            if not path.is_file():
                #Enter when path is not a file
                continue
            if not is_supported(path):
                #Enter when file is not supported
                continue
            
            # print(f"Found supported file: {path}") # Debug

            resolved_path = path.resolve() # convert any relative or shorthand file path into a fully qualified, canonical absolute path
            if resolved_path in seen_paths:
                logging.warning(f"Duplicate file found (skipping): {resolved_path}")
                continue
            seen_paths.add(resolved_path)

            # at this point, we have a supported file that we haven't seen before, 
            # so we check it and add the record to the list
            record =check_file(path)
            records.append(record)
            file_count += 1

            if (record.errors):
                logging.warning(f"File has issues: {path} - Errors:\n{record.errors}")
                continue
        
        logging.info(f"Found {file_count} supported files in {source}")

    logging.info(f"Total files to process: {len(records)}")
    return records