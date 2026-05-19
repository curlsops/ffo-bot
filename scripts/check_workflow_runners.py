#!/usr/bin/env python3
import pathlib
import re
import sys

WANT = "blacksmith-2vcpu-ubuntu-2404"
RUNS_ON = re.compile(r"^\s*runs-on:\s*(.+?)\s*(?:#.*)?$")


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    workflows = root / ".github" / "workflows"
    errors: list[str] = []
    paths = sorted(workflows.glob("*.yml")) + sorted(workflows.glob("*.yaml"))
    for path in paths:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = RUNS_ON.match(line)
            if not m:
                continue
            val = m.group(1).strip().strip('"').strip("'")
            if "${{" in val:
                continue
            if val != WANT:
                rel = path.relative_to(root)
                errors.append(f"{rel}:{lineno}: runs-on is {val!r}, expected {WANT!r}")
    if errors:
        for msg in errors:
            print(msg, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
