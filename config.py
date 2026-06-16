"""
constants, supported extensions
"""

from pathlib import Path

# Extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".heic", ".png", ".tiff", ".tif", ".webp"} # maybe add  ".gif"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}

ALL_SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS # return a new set containing all unique elements from the original sets

# Hashing

HASH_ALGORITHM = "sha256"
HASH_CHUNK_SIZE = 65536 # 64KB


# output folder names
#use the zero padded month numbers to ensure the sort order is always correct
MONTH_NAMES = {
    1: "01 January",
    2: "02 February",
    3: "03 March",
    4: "04 April",
    5: "05 May",
    6: "06 June",
    7: "07 July",
    8: "08 August",
    9: "09 September",
    10: "10 October",
    11: "11 November",
    12: "12 December"
}

# Fallback folder for files where we couldn't determine a date
UNKNOWN_DATE_FOLDER = "Unknown Date"

