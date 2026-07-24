from vgit.resources import resource_path

_VERSION_FILE = resource_path('vgit', 'version.txt')

try:
    with open(_VERSION_FILE, 'r', encoding='utf-8') as _f:
        __version__ = _f.read().strip()
except OSError:
    __version__ = '0.0'
