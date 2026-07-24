#!/usr/bin/env python3
"""VisualGit - a simple git GUI client."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vgit.app import VisualGitApp


def main():
    app = VisualGitApp()
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
