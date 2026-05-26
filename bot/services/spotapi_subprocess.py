import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from bot.services.spotapi_sync import SPOTAPI_OPERATIONS

logger = logging.getLogger(__name__)

_APP_ROOT = Path(__file__).resolve().parents[2]
WORKER_MODULE = "bot.services.spotapi_worker"


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    root = str(_APP_ROOT)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root if not existing else f"{root}{os.pathsep}{existing}"
    return env


def decode_worker_response(stdout: bytes) -> list[str] | str | None:
    if not stdout.strip():
        return None
    payload = json.loads(stdout.decode())
    if not isinstance(payload, dict) or not payload.get("ok"):
        return None
    return payload.get("result")


async def run_spotapi_subprocess(
    operation: str,
    entity_id: str,
    *,
    timeout_sec: float,
) -> list[str] | str | None:
    if operation not in SPOTAPI_OPERATIONS:
        raise ValueError(f"unknown SpotAPI operation: {operation}")
    request = json.dumps({"operation": operation, "id": entity_id}).encode()
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        WORKER_MODULE,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(_APP_ROOT),
        env=_subprocess_env(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(request), timeout=timeout_sec)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning("SpotAPI worker timed out operation=%s", operation)
        return None

    if proc.returncode == 0:
        try:
            return decode_worker_response(stdout)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning("SpotAPI worker returned invalid JSON operation=%s: %s", operation, e)
            return None

    rc = proc.returncode
    if rc is not None and rc < 0:
        logger.warning(
            "SpotAPI worker killed by signal %s operation=%s",
            -rc,
            operation,
        )
    elif stderr:
        logger.debug(
            "SpotAPI worker exited %s: %s",
            rc,
            stderr.decode(errors="replace")[:500],
        )
    return None
