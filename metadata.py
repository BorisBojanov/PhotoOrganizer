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
from pillow_heif import register_heif_opener

from config import VIDEO_EXTENSIONS, IMAGE_EXTENSIONS
from models import FileRecord

register_heif_opener() # Register the HEIF opener for Pillow to handle HEIC files

def parse_exif_date(date_str: str)-> datetime | None:
    """Parse EXIF date format: 'YYYY:MM:DD HH:MM:SS' """
    try:
        date = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
        return date
    except ValueError, AttributeError:
        logging.warning(f"Failed to parese EXIF date: {date_str}")
        return None
    

def parse_date_from_filename(path: Path) -> datetime | None:
    """Try to find a date from the path using common filename patterns
        #Idea is to implament some sort of template question to set this up for user. 

    /All_Photos/2021_01/IMG....
    /Google_Photos/Photos from 2026/IMG.....
    /Boris's iPhone/camping 2024/01a08ac12f0ea1b2e6cd51f0762ce467a9931b71c1.jpg
    /Videos/Fencing Videos/AlbertaCup2022/V_20220604_144001_OC0.mp4
    /Videos/Fencing Videos/20181230_170449.mp4
    /Videos/VID_20161126_100726.mp4
    """
    name = path.stem # .stem gives name without extension
    
    patterns = [
        # date and time: yyyy_mm_dd_HH_MM_SS or with -
        r"(\d{4})[_\-](\d{2})[_\-](\d{2})[_\-](\d{2})[_\-](\d{2})[_\-](\d{2})",
        # date only: yyyy_mm_dd
        r"(\d{4})[_\-](\d{2})[_\-](\d{2})",
        # date time compact:
        r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})"
        # date compact:
        r"(\d{4})(\d{2})(\d{2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, name)
        if match:
            parts = [int(x) for x in match.groups()]
            
            try:
                if len(parts) == 6:
                    return datetime(parts[0], parts[1], parts[2], parts[3], parts[4], parts[5])
                else: 
                    return datetime(parts[0], parts[1], parts[2])
            except ValueError:
                continue # If the date parts are invalid, try the next pattern
    return None

def parse_gps_to_decimal(values, ref: str) -> float:
    """Convert GPS: [51, 6, 9636/625] to decimal degrees, and apply N/S/E/W reference."""
    d = values[0].num / values[0].den
    m = values[1].num / values[1].den
    s = values[2].num / values[2].den
    decimal = d + (m / 60) + (s / 3600)
    if ref in ["S", "W"]:
        decimal = -decimal
    round(decimal, 6)
    return decimal

def read_image_metadata(record: FileRecord)-> None:
    """Read EXIF data from image files using exifread."""
    try:
        with open(record.path, 'rb') as f:
            # Dict of all tags
            tags = exifread.process_file(f, stop_tag="EXIF ImageUniqueID", details=False)

        #Check the date taken tags
        """ Example tag key values for 20200705_222324_037.jpg

        "EXIF DateTimeOriginal": 2020:07:05 22:23:28
        "EXIF DateTimeDigitized": 2020:07:05 22:23:28
        "Image DateTime": 2020:07:05 22:23:28

        EXIF DateTimeOriginal: When the actual physical scene was shot.
        EXIF DateTimeDigitized: When the image data was digitized (often same as DateTimeOriginal).

        Image DateTime: When the image data or metadata was last saved/edited. (Not reliable for original capture date, can change if file is edited or copied.)
        """
        metadataTags = ["EXIF DateTimeOriginal", "EXIF DateTimeDigitized"]

        for tag in metadataTags:
            if tag in tags:
                parsed = parse_exif_date(str(tags.get(tag))) # uses .get to avoid KeyError.
                if parsed:
                    # add to record object and break out of loop
                    record.date_taken = parsed

        #Camera make and model
        if "Image Make" in tags:
            record.camera_make = str(tags.get("Image Make")).strip()
        if "Image Model" in tags:
            record.camera_model = str(tags.get("Image Model")).strip()

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
        if "GPS GPSLongitude" in tags and "GPS GPSLatitude" in tags:
            # try:
                lat = list[tags.get("GPS GPSLatitude")]

    except Exception as e:
        pass
    
    
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


if __name__ == "__main__":
    test()