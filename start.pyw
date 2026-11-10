"""Peluncur ClixMax.

Windows: klik dua kali berkas ini (atau shortcut-nya).
macOS/Linux: python3 start.pyw
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from clixmax.app import main  # noqa: E402

if __name__ == "__main__":
    main()
