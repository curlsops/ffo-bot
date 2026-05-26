import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

from bot.services.spotapi_sync import SPOTAPI_OPERATIONS
from bot.services.tls_client_alpine import spotapi_native_supported
from bot.utils.telemetry import logging_extra

logger = logging.getLogger(__name__)

_APP_ROOT = Path(__file__).resolve().parents[2]
WORKER_MODULE = "bot.services.spotapi_worker"


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    root = str(_APP_ROOT)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root if not existing else f"{root}{os.pathsep}{existing}"
    return env


def _signal_name(signum: int) -> str:
    try:
        return signal.Signals(signum).name
    except (ValueError, AttributeError):
        return str(signum)


def _log_worker_failure(
    operation: str,
    returncode: int | None,
    stderr: bytes,
) -> None:
    err = stderr.decode(errors="replace").strip()
    snippet = f" stderr={err[:500]!r}" if err else ""
    if returncode is not None and returncode < 0:
        sig = -returncode
        logger.warning(
            "SpotAPI worker killed by %s (signal %s) operation=%s%s",
            _signal_name(sig),
            sig,
            operation,
            snippet,
            extra=logging_extra(
                feature="spotify",
                spotapi_failure="sigsegv" if sig == signal.SIGSEGV else "signal",
                spotapi_signal=sig,
            ),
        )
        return
    logger.warning(
        "SpotAPI worker exited %s operation=%s%s",
        returncode,
        operation,
        snippet,
        extra=logging_extra(
            feature="spotify",
            spotapi_failure="exit_error",
            spotapi_exit_code=returncode if returncode is not None else -1,
        ),
    )


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
    if not spotapi_native_supported():
        logger.warning(
            "SpotAPI unavailable on musl (tls_client native library); operation=%s",
            operation,
            extra=logging_extra(feature="spotify", spotapi_failure="musl_unsupported"),
        )
        return None
    request = json.dumps({"operation": operation, "id": entity_id}).encode()
    try:
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
    except FileNotFoundError:
        logger.warning(
            "SpotAPI worker executable not found: %s operation=%s",
            sys.executable,
            operation,
            extra=logging_extra(feature="spotify", spotapi_failure="enoent"),
        )
        return None
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(request), timeout=timeout_sec)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning(
            "SpotAPI worker timed out operation=%s",
            operation,
            extra=logging_extra(feature="spotify", spotapi_failure="timeout"),
        )
        return None

    if proc.returncode == 0:
        try:
            return decode_worker_response(stdout)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(
                "SpotAPI worker returned invalid JSON operation=%s: %s",
                operation,
                e,
                extra=logging_extra(feature="spotify", spotapi_failure="bad_json"),
            )
            return None

    _log_worker_failure(operation, proc.returncode, stderr)
    return None
