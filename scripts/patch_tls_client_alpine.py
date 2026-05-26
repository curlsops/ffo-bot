#!/usr/bin/env python3
"""Patch tls_client to load the musl amd64 shared library on x86_64 Alpine."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <site-packages>", file=sys.stderr)
        return 2

    cffi = Path(sys.argv[1]) / "tls_client" / "cffi.py"
    if not cffi.is_file():
        print(f"skip: {cffi} not found", file=sys.stderr)
        return 0

    text = cffi.read_text()
    needle = "    elif \"x86\" in machine():\n        file_ext = '-x86.so'"
    insert = (
        '    elif machine() in ("x86_64", "amd64"):\n'
        "        file_ext = '-amd64.so'\n"
        '    elif "x86" in machine():\n'
        "        file_ext = '-x86.so'"
    )
    if "file_ext = '-amd64.so'" in text:
        print("already patched")
        return 0
    if needle not in text:
        print(f"skip: unexpected tls_client cffi layout in {cffi}", file=sys.stderr)
        return 1

    cffi.write_text(text.replace(needle, insert, 1))
    print(f"patched {cffi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
