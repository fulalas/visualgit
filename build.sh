#!/bin/sh
# Build a single-file VisualGit binary with PyInstaller.
#
# Produces ./visualgit (Linux x86_64) in the project root. Everything else
# lives under build/ and is disposable: the PyInstaller work dir (build/work),
# the generated spec (build/visualgit.spec), and a build-only virtualenv
# (build/venv, created with --system-site-packages so it inherits the system
# PyGObject/GTK while keeping the system Python untouched). Delete build/
# anytime to reclaim space; ./build.sh recreates it.
#
# Run:  ./build.sh
set -e
cd "$(dirname "$0")"
ROOT="$(pwd)"

BUILD=build
VENV="$BUILD/venv"

if [ ! -x "$VENV/bin/pyinstaller" ]; then
    echo "Setting up build virtualenv in $VENV ..."
    python3 -m venv --system-site-packages "$VENV"
    "$VENV/bin/python" -m pip install --disable-pip-version-check -q pyinstaller
fi

echo "Building ..."
# Build config (strip, -OO, module excludes, GTK-data pruning) lives in the
# spec. PyInstaller bundles prebuilt CPython + system GTK .so's + our bytecode
# — it does not compile C/Rust, so CFLAGS/LDFLAGS have nothing to act on.
# UPX, if installed, is picked up automatically (upx=True in the spec).
"$VENV/bin/pyinstaller" --noconfirm \
    --workpath "$BUILD/work" \
    --distpath "$ROOT" \
    packaging/visualgit.spec

echo "Done -> ./visualgit"
