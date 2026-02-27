#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys


def main() -> int:
    if shutil.which("sops") is None:
        print("sops is not installed. Please install sops to use this hook.", file=sys.stderr)
        return 1

    if not os.environ.get("SOPS_AGE_KEY_FILE") and not os.environ.get("SOPS_AGE_KEY"):
        print("SOPS_AGE_KEY_FILE or SOPS_AGE_KEY must be set for encryption.", file=sys.stderr)
        return 1

    files = sys.argv[1:]
    if not files:
        return 0

    for path in files:
        if not os.path.isfile(path):
            continue
        try:
            subprocess.run(
                ["sops", "--encrypt", "--in-place", path],
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            print(f"sops encryption failed for {path}: {exc}", file=sys.stderr)
            return exc.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
