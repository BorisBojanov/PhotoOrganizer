"""
EXIF + video metadata reading

Take a Filerecord object that the scanner created and fill in:
    date_taken, 
    date_source, 
    camera_make, 
    camera_model
    and any other metadata we can get from the file.

It only builds connections to the objects, It never touches the filesystem beyond reading.

EXIF
Not every file has EXIF. Only iPhone photos.
1. EXIF DateTimeOriginal   ← most accurate, when present
2. Video container date    ← for MP4/MOV via ffprobe
3. File's "filename.jpeg.supplemental-met.json" sidecar file    ← if it exists, it may have a "date_taken" field
4. Parse date from filename ← Like "IMG_20230415_..." or "2023-04-15..."
5. File's "Content created" date    ← last resort, least accurate but always present.

First to succeed is set as date_taken, and the source is recorded in date_source.

Video
This part needs the following libraries: Pillow pillow-heif exifread

For videos, ffprobe must be installed at the system level (it's part of ffmpeg):
macOS: brew install ffmpeg
Linux (Raspberry Pi): sudo apt install ffmpeg
Windows: download from ffmpeg.org and add to PATH

"""

import json
import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

import exifread
from PIL import Image
from PIL import Image, ExifTags
from pillow_heif import register_heif_opener

from config import VIDEO_EXTENSIONS, IMAGE_EXTENSIONS
from models import FileRecord

register_heif_opener() # Register the HEIF opener for Pillow to handle HEIC files

def parse_exif_date(date_str: str)-> datetime | None:
    """Parse EXIF date format: 'YYYY:MM:DD HH:MM:SS' """
    try:
        date = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
        return date
    except (ValueError, AttributeError) as e:
        logging.warning(f"Failed to parese EXIF date: {date_str}")
        return None
    

def parse_date_from_filename(path: Path) -> datetime | None:
    """
    Look for a year (optionally with month) in parent folder names.
    Handles: 'Photos from 2016', '2021_01', '2016', 'camping 2024'.
    Checks nearest parent first. Returns Jan 1 of that year (or the 1st
    of the month if found) — coarse, but far better than the copy date.

    Try to find a date from the path using common filename patterns
        #Idea is to implament some sort of template question to set this up for user. 

    /All_Photos/2021_01/IMG....
    /Google_Photos/Photos from 2026/IMG.....
    /Boris's iPhone/camping 2024/01a08ac12f0ea1b2e6cd51f0762ce467a9931b71c1.jpg
    /Videos/Fencing Videos/AlbertaCup2022/V_20220604_144001_OC0.mp4
    /Videos/Fencing Videos/20181230_170449.mp4
    /Videos/VID_20161126_100726.mp4
    """
    name = path.stem # .stem gives name without extension
    
    # patterns = [
    #     # date and time: yyyy_mm_dd_HH_MM_SS or with -
    #     r"(\d{4})[_\-](\d{2})[_\-](\d{2})[_\-](\d{2})[_\-](\d{2})[_\-](\d{2})",
    #     # date only: yyyy_mm_dd
    #     r"(\d{4})[_\-](\d{2})[_\-](\d{2})",
    #     # date time compact:
    #     r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})"
    #     # date compact:
    #     r"(\d{4})(\d{2})(\d{2})",
    # ]

    # for pattern in patterns:
    #     match = re.search(pattern, name)
    #     if match:
    #         parts = [int(x) for x in match.groups()]
            
    #         try:
    #             if len(parts) == 6:
    #                 return datetime(parts[0], parts[1], parts[2], parts[3], parts[4], parts[5])
    #             else: 
    #                 return datetime(parts[0], parts[1], parts[2])
    #         except ValueError:
    #             continue # If the date parts are invalid, try the next pattern

    for parent in path.parents:
        name = parent.name

        # 'YYYY_MM' or 'YYYY-MM' → year + month
        match = re.fullmatch(r"(\d{4})[_\-](\d{2})", name)
        if match:
            year, month = int(match.group(1)), int(match.group(2))
            if 1990 <= year <= datetime.now().year and 1 <= month <= 12:
                return datetime(year, month, 1)

        # any standalone 4-digit year in the folder name
        match = re.search(r"\b(19[9]\d|20[0-4]\d)\b", name)
        if match:
            year = int(match.group(1))
            return datetime(year, 1, 1)

    return None

# ── Image metadata ────────────────────────────────────────────────────────────

def read_image_metadata(record: FileRecord) -> None:
    """Read EXIF via Pillow — works for JPEG, HEIC, PNG, TIFF alike."""
    try:
        with Image.open(record.path) as img:
            exif = img.getexif()
            if not exif:
                return  # no EXIF at all — fallback chain will handle it

            # Date lives in the Exif sub-IFD, camera info in the main IFD
            exif_ifd = exif.get_ifd(ExifTags.IFD.Exif)

            #Check the date taken tags
            """ Example tag key values for 20200705_222324_037.jpg

            "EXIF DateTimeOriginal": 2020:07:05 22:23:28
            "EXIF DateTimeDigitized": 2020:07:05 22:23:28
            "Image DateTime": 2020:07:05 22:23:28

            EXIF DateTimeOriginal: When the actual physical scene was shot.
            EXIF DateTimeDigitized: When the image data was digitized (often same as DateTimeOriginal).

            Image DateTime: When the image data or metadata was last saved/edited. (Not reliable for original capture date, can change if file is edited or copied.)
            """
            date_str = (
                exif_ifd.get(ExifTags.Base.DateTimeOriginal)
                or exif_ifd.get(ExifTags.Base.DateTimeDigitized)
                or exif.get(ExifTags.Base.DateTime)
            )
            if date_str:
                parsed = parse_exif_date(str(date_str))
                if parsed:
                    record.date_taken = parsed
                    record.data_source = "exif"

            make = exif.get(ExifTags.Base.Make)
            model = exif.get(ExifTags.Base.Model)
            if make:
                record.camera_make = str(make).strip()
            if model:
                record.camera_model = str(model).strip()

            # GPS data
            """
            GPS GPSVersionID: [2, 2, 0, 0]
            GPS GPSLatitudeRef: N
            GPS GPSLatitude: [51, 6, 9636/625]
            GPS GPSLongitudeRef: W
            GPS GPSLongitude: [114, 5, 209519/5000]
            GPS GPSAltitudeRef: 0
            GPS GPSAltitude: 1136697/1000
            GPS GPSTimeStamp: [4, 23, 1]
            GPS GPSDate: 2020:07:06
            Image GPSInfo: 5964
            """
            gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
            if gps:
                try:
                    lat = pillow_gps_to_decimal(gps.get(2), str(gps.get(1, "N")))
                    lon = pillow_gps_to_decimal(gps.get(4), str(gps.get(3, "E")))
                    if lat is not None and lon is not None:
                        record.gps_lat = lat
                        record.gps_lon = lon
                except Exception:
                    pass

    except Exception as e:
        record.errors.append(f"Image metadata read failed: {e}")


def pillow_gps_to_decimal(values, ref: str) -> float:
    """Convert GPS: [51, 6, 9636/625] to decimal degrees, and apply N/S/E/W reference."""
    d = values[0].num / values[0].den
    m = values[1].num / values[1].den
    s = values[2].num / values[2].den
    decimal = d + (m / 60) + (s / 3600)
    if ref in ["S", "W"]:
        decimal = -decimal
    round(decimal, 6)
    return decimal


# ── Video metadata ────────────────────────────────────────────────────────────

def read_video_metadata(record: FileRecord) -> None:
    """Use ffprobe to read creation_time from video container."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_entries", "format_tags=creation_time",
            str(record.path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)
        creation_time = data.get("format", {}).get("tags", {}).get("creation_time")

        if creation_time:
            # ffprobe returns ISO 8601: "2023-04-15T14:32:01.000000Z"
            record.date_taken = datetime.fromisoformat(
                creation_time.replace("Z", "+00:00")
            ).replace(tzinfo=None)
            record.data_source = "video_container"

    except FileNotFoundError:
        record.errors.append("ffprobe not found — install ffmpeg to read video dates")
    except Exception as e:
        record.errors.append(f"Video metadata read failed: {e}")

# -- Sidecar metadata (JSON) ---
SIDECAR_SUFFIXES = [
    ".supplemental-metadata.json",
    ".supplemental-meta.json",
    ".json",
]

def find_sidecar(path: Path) -> Path | None:
    """
    Locate a Google Takeout / XMP sidecar for this media file.
    Tries exact conventions first, then a prefix glob for Google's
    truncated filenames (it caps metadata names around 51 chars).
    """
    # IMG_1234.JPG.supplemental-metadata.json  /  IMG_1234.JPG.json
    for suffix in SIDECAR_SUFFIXES:
        candidate = path.with_name(path.name + suffix)
        if candidate.exists():
            return candidate

    # IMG_1234.json  (extension replaced rather than appended)
    candidate = path.with_suffix(".json")
    if candidate.exists():
        return candidate

    # XMP sidecars from Lightroom / darktable
    for candidate in (path.with_name(path.name + ".xmp"), path.with_suffix(".xmp")):
        if candidate.exists():
            return candidate

    # Truncated Google names: match anything starting with the media filename
    matches = sorted(path.parent.glob(f"{path.name}*.json"))
    if matches:
        return matches[0]

    return None

def read_sidecar_metadata(record: FileRecord) -> None:
    """Read photoTakenTime from a Google Takeout JSON sidecar."""
    if not record.sidecar_path or record.sidecar_path.suffix.lower() != ".json":
        return
    try:
        with open(record.sidecar_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        taken = data.get("photoTakenTime") or data.get("creationTime")
        if taken and "timestamp" in taken:
            record.date_taken = datetime.fromtimestamp(int(taken["timestamp"]))
            record.data_source = "sidecar"

        geo = data.get("geoData") or {}
        if geo.get("latitude") and geo.get("longitude"):
            record.gps_lat = round(float(geo["latitude"]), 6)
            record.gps_lon = round(float(geo["longitude"]), 6)

    except Exception as e:
        record.errors.append(f"Sidecar read failed: {e}")

# ── Public API ────────────────────────────────────────────────────────────────
def enrich_metadata(record: FileRecord) -> FileRecord:
    """
    Fill in date_taken and camera info on a FileRecord.
    Skips files that don't exist or are already known to be problematic.
    """
    if not record.exists or record.size_bytes == 0:
        return record

    suffix = record.path.suffix.lower()

    if suffix in VIDEO_EXTENSIONS:
        read_video_metadata(record)
    else:
        read_image_metadata(record)

    # after read_video_metadata / read_image_metadata:
    record.sidecar_path = find_sidecar(record.path)
    record.has_sidecar = record.sidecar_path is not None

    if record.date_taken is None and record.has_sidecar:
        read_sidecar_metadata(record)

    # then filename → folder → mtime fallbacks
    # Fallback chain if primary method found nothing
    if record.date_taken is None:
        parsed = parse_date_from_filename(record.path)
        if parsed:
            record.date_taken = parsed
            record.data_source = "filename"

    if record.date_taken is None:
        record.date_taken = datetime.fromtimestamp(record.path.stat().st_mtime)
        record.data_source = "file_modified"
        logging.debug(f"Using file modified date for: {record.path.name}")

    return record



def test():
    mypath="20200705_222324_037.jpg"
    with open(mypath, 'rb') as f:
        tags = exifread.process_file(f, stop_tag="GPS GPSLongitude", details=False)
    
    # 1. Print all available tags
    # for tag_key, tag_value in tags.items():
    #     print(f"{tag_key}: {tag_value}")
    """
    Image ImageWidth: 4032
    Image ImageLength: 1960
    Image Make: samsung
    Image Model: SM-G950W
    Image Orientation: Horizontal (normal)
    Image XResolution: 72
    Image YResolution: 72
    Image ResolutionUnit: Pixels/Inch
    Image Software: G950WVLS7CTC1
    Image DateTime: 2020:07:05 22:23:28
    Image YCbCrPositioning: Centered
    Image ExifOffset: 238
    GPS GPSVersionID: [2, 2, 0, 0]
    GPS GPSLatitudeRef: N
    GPS GPSLatitude: [51, 6, 9636/625]
    GPS GPSLongitudeRef: W
    GPS GPSLongitude: [114, 5, 209519/5000]
    GPS GPSAltitudeRef: 0
    GPS GPSAltitude: 1136697/1000
    GPS GPSTimeStamp: [4, 23, 1]
    GPS GPSDate: 2020:07:06
    Image GPSInfo: 5964
    Thumbnail ImageWidth: 496
    Thumbnail ImageLength: 240
    Thumbnail Compression: JPEG (old-style)
    Thumbnail Orientation: Horizontal (normal)
    Thumbnail XResolution: 72
    Thumbnail YResolution: 72
    Thumbnail ResolutionUnit: Pixels/Inch
    Thumbnail JPEGInterchangeFormat: 6300
    Thumbnail JPEGInterchangeFormatLength: 6876
    EXIF ExposureTime: 1/10
    EXIF FNumber: 17/10
    EXIF ExposureProgram: Program Normal
    EXIF ISOSpeedRatings: 200
    EXIF ExifVersion: 0220
    EXIF DateTimeOriginal: 2020:07:05 22:23:28
    EXIF DateTimeDigitized: 2020:07:05 22:23:28
    EXIF ComponentsConfiguration: YCbCr
    EXIF ShutterSpeedValue: 3321/1000
    EXIF ApertureValue: 153/100
    EXIF BrightnessValue: -32/25
    EXIF ExposureBiasValue: 0
    EXIF MaxApertureValue: 153/100
    EXIF MeteringMode: CenterWeightedAverage
    EXIF LightSource: Unknown
    EXIF Flash: Flash did not fire
    EXIF FocalLength: 17/4
    EXIF FlashPixVersion: 0100
    EXIF ColorSpace: sRGB
    EXIF ExifImageWidth: 4032
    EXIF ExifImageLength: 1960
    Interoperability InteroperabilityIndex: R98
    Interoperability InteroperabilityVersion: [48, 49, 48, 48]
    EXIF InteroperabilityOffset: 5934
    EXIF SensingMethod: One-chip color area
    EXIF SceneType: Directly Photographed
    EXIF ExposureMode: Auto Exposure
    EXIF WhiteBalance: Auto
    EXIF FocalLengthIn35mmFilm: 26
    EXIF SceneCaptureType: Standard
    EXIF ImageUniqueID: F12QSJA00SM F12QSKB01SB
    JPEGThumbnail: b'LOTS OF BINARY DATA'
    """
    # # 2. Safely get a specific tag
    date_taken = tags.get('EXIF DateTimeOriginal')
    lat = tags.get("GPS GPSLatitude")
    if date_taken:
        print(f"Lat: {lat}") #>>> Date: 2020:07:05 22:23:28


# if __name__ == "__main__":
#     test()