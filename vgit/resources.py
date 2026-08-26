import os
import sys


def resource_path(*parts):
    # A PyInstaller bundle extracts data files under sys._MEIPASS instead of
    # the project root.
    base = getattr(sys, '_MEIPASS', None)
    if base is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)
