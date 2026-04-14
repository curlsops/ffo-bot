import asyncio
import json
import logging
import re
import socket
import struct
from dataclasses import dataclass, field

from config.settings import Settings

logger = logging.getLogger(__name__)

RCON_PACKET_LOGIN = 3
RCON_PACKET_COMMAND = 2


class MinecraftRCONError(Exception):
    pass


def _log_rcon_target_failure(target: RconTarget, err: BaseException, *, context: str) -> None:
    logger.warning(
        "%s: unable to reach RCON target_id=%s host=%s port=%s: %s",
        context,
        target.id,
        target.host,
        target.port,
        err,
    )


@dataclass
class RconTarget:
    id: str
    host: str
    port: int
    password: str

    def __repr__(self) -> str:
        return f"RconTarget(id={self.id!r}, host={self.host!r}, port={self.port})"


@dataclass(frozen=True)
class WhitelistListMergeResult:
    usernames: list[str]
    reachable_target_ids: tuple[str, ...]
    unreachable_target_ids: tuple[str, ...]


@dataclass
class TargetPushResult:
    target_id: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    error: str | None = None


def _parse_rcon_targets(settings: Settings) -> list[RconTarget]:
    if not settings.feature_minecraft_whitelist:
        return []
    raw = settings.minecraft_rcon_targets
    if raw and str(raw).strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("Invalid minecraft_rcon_targets JSON: %s", e)
            data = None
        if isinstance(data, list) and data:
            result: list[RconTarget] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                tid = str(item.get("id") or item.get("name") or f"server{len(result)}")
                host = item.get("host")
                password = item.get("password")
                port = int(item.get("port", 25575))
                if host and password:
                    result.append(RconTarget(id=tid, host=host, port=port, password=password))
            if result:
                return result
    return _legacy_single_target(settings)


def _legacy_single_target(settings: Settings) -> list[RconTarget]:
    host = settings.minecraft_rcon_host
    password = settings.minecraft_rcon_password
    if host and password:
        return [
            RconTarget(
                id="default",
                host=host,
                port=int(settings.minecraft_rcon_port),
                password=password,
            )
        ]
    return []


def _send_rcon_packet(sock: socket.socket, packet_type: int, payload: str, req_id: int) -> None:
    data = payload.encode("utf-8") + b"\x00\x00"
    packet = struct.pack("<iii", len(data) + 8, req_id, packet_type) + data
    sock.sendall(packet)


def _recv_rcon_packet(sock: socket.socket) -> tuple[int, int, str]:
    header = sock.recv(12)
    if len(header) < 12:
        raise MinecraftRCONError("Connection closed or incomplete header")
    length, req_id, packet_type = struct.unpack("<iii", header)
    body_len = length - 8
    body = b""
    while len(body) < body_len:
        chunk = sock.recv(body_len - len(body))
        if not chunk:
            break
        body += chunk
    response = body.rstrip(b"\x00").decode("utf-8", errors="replace")
    return req_id, packet_type, response


def _rcon_command(host: str, port: int, password: str, command: str, timeout: float = 10.0) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        try:
            sock.connect((host, port))
            _send_rcon_packet(sock, RCON_PACKET_LOGIN, password, 1)
            req_id, _, _ = _recv_rcon_packet(sock)
            if req_id == -1:
                raise MinecraftRCONError("RCON authentication failed")
            _send_rcon_packet(sock, RCON_PACKET_COMMAND, command, 2)
            _, _, response = _recv_rcon_packet(sock)
            return response
        except TimeoutError as e:
            raise MinecraftRCONError(
                f"RCON connection timed out ({host}:{port}); check host, port, firewall, and pod network"
            ) from e
        except OSError as e:
            raise MinecraftRCONError(f"RCON connection failed ({host}:{port}): {e}") from e
    finally:
        sock.close()


class MinecraftRCONClient:
    def __init__(self, settings: Settings):
        self._targets: list[RconTarget] = _parse_rcon_targets(settings)
        raw_timeout = getattr(settings, "minecraft_rcon_connect_timeout_seconds", 10.0)
        if isinstance(raw_timeout, (int, float)) and not isinstance(raw_timeout, bool):
            t = float(raw_timeout)
        else:
            t = 10.0
        self._connect_timeout = max(1.0, min(120.0, t))

    def _is_configured(self) -> bool:
        return bool(self._targets)

    async def _run_rcon_on(self, target: RconTarget, command: str) -> str:
        if not self._is_configured():
            raise MinecraftRCONError("Minecraft RCON not configured")

        def _sync_command() -> str:
            return _rcon_command(
                target.host,
                target.port,
                target.password,
                command,
                timeout=self._connect_timeout,
            )

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_command)

    async def _run_rcon(self, command: str) -> str:
        if not self._targets:
            raise MinecraftRCONError("Minecraft RCON not configured")
        return await self._run_rcon_on(self._targets[0], command)

    async def _broadcast_command(self, command: str) -> str:
        if not self._targets:
            raise MinecraftRCONError("Minecraft RCON not configured")

        async def _one(t: RconTarget) -> tuple[RconTarget, str | None, MinecraftRCONError | None]:
            try:
                r = await self._run_rcon_on(t, command)
                return (t, r, None)
            except MinecraftRCONError as e:
                _log_rcon_target_failure(t, e, context="rcon_broadcast")
                return (t, None, e)

        rows = await asyncio.gather(*[_one(t) for t in self._targets])
        successes: list[tuple[str, str]] = []
        failures: list[tuple[str, str]] = []
        for t, r, err in rows:
            if err is not None:
                failures.append((t.id, str(err)))
            else:
                assert r is not None
                successes.append((t.id, r))
        if not successes:
            raise MinecraftRCONError(
                "All targets failed: " + "; ".join(f"{k}: {v}" for k, v in failures)
            )
        lines = [f"{tid}: {r}" for tid, r in successes]
        if failures:
            lines.extend(f"{tid}: failed ({err})" for tid, err in failures)
        return "\n".join(lines)

    async def whitelist_add(self, username: str) -> str:
        return await self._broadcast_command(f"whitelist add {username}")

    async def whitelist_remove(self, username: str) -> str:
        return await self._broadcast_command(f"whitelist remove {username}")

    async def whitelist_list(self) -> str:
        return await self._run_rcon("whitelist list")

    async def whitelist_list_merge(self) -> WhitelistListMergeResult:
        if not self._is_configured():
            raise MinecraftRCONError("Minecraft RCON not configured")

        async def _one(t: RconTarget) -> tuple[RconTarget, str | None, BaseException | None]:
            try:
                r = await self._run_rcon_on(t, "whitelist list")
                return (t, r, None)
            except Exception as e:
                _log_rcon_target_failure(t, e, context="whitelist_list_merge")
                return (t, None, e)

        rows = await asyncio.gather(*[_one(t) for t in self._targets])
        by_lower: dict[str, str] = {}
        reachable: list[str] = []
        unreachable: list[str] = []
        for t, resp, err in rows:
            if err is not None:
                unreachable.append(t.id)
                continue
            reachable.append(t.id)
            for name in parse_whitelist_list_response(resp or ""):
                low = name.lower()
                if low not in by_lower:
                    by_lower[low] = name
        usernames = sorted(by_lower.values(), key=str.lower)
        return WhitelistListMergeResult(
            usernames=usernames,
            reachable_target_ids=tuple(reachable),
            unreachable_target_ids=tuple(unreachable),
        )

    async def whitelist_on(self) -> str:
        return await self._broadcast_command("whitelist on")

    async def whitelist_off(self) -> str:
        return await self._broadcast_command("whitelist off")

    async def push_master_whitelist(self, master_usernames: list[str]) -> list[TargetPushResult]:
        if not self._is_configured():
            raise MinecraftRCONError("Minecraft RCON not configured")
        master_by_lower = {u.lower(): u for u in master_usernames}
        master_lower = set(master_by_lower.keys())

        async def _push_one(t: RconTarget) -> TargetPushResult:
            tr = TargetPushResult(target_id=t.id)
            try:
                resp = await self._run_rcon_on(t, "whitelist list")
                current = parse_whitelist_list_response(resp)
                current_lower = {u.lower(): u for u in current}
                for u in current:
                    if u.lower() not in master_lower:
                        await self._run_rcon_on(t, f"whitelist remove {u}")
                        tr.removed.append(u)
                for low in master_lower:
                    if low not in current_lower:
                        canon = master_by_lower[low]
                        await self._run_rcon_on(t, f"whitelist add {canon}")
                        tr.added.append(canon)
            except Exception as e:
                tr.error = str(e)
                _log_rcon_target_failure(t, e, context="push_master_whitelist")
            return tr

        return list(await asyncio.gather(*[_push_one(t) for t in self._targets]))


def parse_whitelist_list_response(response: str) -> list[str]:
    response = response.strip()
    m = re.search(r":\s*(.+)$", response, re.DOTALL)
    if not m:
        return []
    names_str = m.group(1).strip()
    if not names_str:
        return []  # pragma: no cover - unreachable: strip() removes trailing ws before regex
    parts = names_str.split(",")
    result = []
    for p in parts:
        s = p.strip()
        if s:
            result.append(s)
    return result
