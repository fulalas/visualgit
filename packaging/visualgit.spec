# -*- mode: python ; coding: utf-8 -*-
# One-file build spec for VisualGit. Built via ../build.sh.
#
# PyInstaller bundles prebuilt CPython + the system GTK .so's + our bytecode;
# it does not compile C/Rust, so CFLAGS/LDFLAGS have nothing to act on. The
# size levers are: strip symbols (strip=True), -OO bytecode (optimize=2),
# excluding unused modules, and — the big one — pruning the icon/cursor/theme
# data PyInstaller's GTK hook over-collects. That data is duplicated from the
# run-time system, which GTK still finds on its normal search path, so dropping
# it from the bundle is safe on a system that has an icon theme installed.
import os

ROOT = os.path.dirname(SPECPATH)

a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, 'vgit', 'version.txt'), 'vgit'),
        (os.path.join(ROOT, 'vgit', 'ui', 'logo.svg'), 'vgit/ui'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter', 'test', 'unittest', 'lib2to3', 'pydoc',
              'distutils', 'setuptools', 'pip'],
    noarchive=False,
    optimize=2,
)

# Drop bundled data the run-time system already provides. GTK keeps the system
# data dirs on its search path, so icons/cursors/themes still resolve.
_DROP_PREFIXES = ('share/icons/', 'share/themes/', 'share/cursors/',
                  'share/locale/', 'share/fonts/')


def _keep(dest):
    d = dest.replace(os.sep, '/')
    return not d.startswith(_DROP_PREFIXES)


a.datas = [t for t in a.datas if _keep(t[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [('O', None, 'OPTION'), ('O', None, 'OPTION')],
    name='visualgit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
