"""
copy files into year/month folders
"""

# import argparse
import os
import shutil
from pathlib import Path
import sys
from PIL import Image
from pillow_heif import register_heif_opener

