"""Locate bundled data files, both when run from source and when frozen
into a PyInstaller one-file bundle (which extracts data under sys._MEIPASS)."""
import os
import sys


def resource_path(*parts):
    base = getattr(sys, '_MEIPASS', None)
    if base is None:
        # Running from source: project root is the parent of the vgit package.
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)
