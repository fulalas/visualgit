import os

_VERSION_FILE = os.path.join(os.path.dirname(__file__), 'version.txt')

try:
    with open(_VERSION_FILE, 'r', encoding='utf-8') as _f:
        __version__ = _f.read().strip()
except OSError:
    __version__ = '0.0'
