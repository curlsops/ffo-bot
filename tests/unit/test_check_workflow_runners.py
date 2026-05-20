import subprocess
import sys
from pathlib import Path


def test_workflow_runner_check_passes() -> None:
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, str(root / "scripts" / "check_workflow_runners.py")],
        cwd=root,
        check=True,
    )
