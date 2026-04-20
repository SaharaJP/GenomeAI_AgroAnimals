from __future__ import annotations

import json
import os
import socket
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlsplit, urlunsplit

from core.infra.runtime_storage import ADULT_RUNTIME_PROFILES, normalize_runtime_profile


SUPPORTED_QUEUE_BACKENDS = {"sqlite", "redis"}
DEFAULT_QUEUE_KEY_PREFIX = "genomeai:queue"


class QueueRuntimeConfigError(RuntimeError):
    """Raised when queue runtime config is unsafe or incomplete."""


@dataclass(frozen=True)
class QueueRuntimeSettings:
    profile: str
    backend: str
    adult_mode: bool
    compat_mode: bool
    redis_dsn: str | None
    redis_password: str | None
    key_prefix: str
    visibility_timeout_sec: int
    idempotency_ttl_sec: int
    claim_block_timeout_sec: int

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["redis_dsn"] = redact_redis_dsn(self.redis_dsn)
        payload["redis_password"] = "***" if self.redis_password else None
        return payload


@dataclass(frozen=True)
class QueueRuntimeDiagnostics:
    profile: str
    backend: str
    adult_mode: bool
    compat_mode: bool
    embedded_worker_allowed: bool
    dedicated_worker_required: bool
    redis_dsn_present: bool
    redis_dsn_redacted: str | None
    broker_status: str
    key_prefix: str
    visibility_timeout_sec: int
    idempotency_ttl_sec: int
    claim_block_timeout_sec: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QueueEnvelope:
    job_id: int
    public_job_id: str
    queue_name: str
    kind: str
    tenant_id: str
    user_id: int | None
    data_version: str | None
    run_id: str | None
    attempt_no: int
    max_attempts: int
    enqueued_at: str
    raw_payload: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": int(self.job_id),
            "public_job_id": str(self.public_job_id),
            "queue_name": str(self.queue_name),
            "kind": str(self.kind),
            "tenant_id": str(self.tenant_id),
            "user_id": int(self.user_id) if self.user_id not in (None, "") else None,
            "data_version": self.data_version,
            "run_id": self.run_id,
            "attempt_no": int(self.attempt_no),
            "max_attempts": int(self.max_attempts),
            "enqueued_at": str(self.enqueued_at),
        }

    def serialize(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_payload(cls, payload: str) -> "QueueEnvelope":
        raw = str(payload or "")
        obj = json.loads(raw)
        return cls(
            job_id=int(obj.get("job_id") or 0),
            public_job_id=str(obj.get("public_job_id") or ""),
            queue_name=str(obj.get("queue_name") or "default"),
            kind=str(obj.get("kind") or "job"),
            tenant_id=str(obj.get("tenant_id") or "default"),
            user_id=int(obj.get("user_id")) if obj.get("user_id") not in (None, "") else None,
            data_version=str(obj.get("data_version") or "").strip() or None,
            run_id=str(obj.get("run_id") or "").strip() or None,
            attempt_no=int(obj.get("attempt_no") or 0),
            max_attempts=max(1, int(obj.get("max_attempts") or 1)),
            enqueued_at=str(obj.get("enqueued_at") or ""),
            raw_payload=raw,
        )


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_secret(*, env_name: str) -> str:
    direct = str(os.environ.get(env_name, "") or "").strip()
    if direct:
        return direct
    file_var = f"{env_name}_FILE"
    file_path = str(os.environ.get(file_var, "") or "").strip()
    if not file_path:
        return ""
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise QueueRuntimeConfigError(f"{file_var} указывает на отсутствующий файл: {file_path}")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise QueueRuntimeConfigError(f"{file_var} содержит пустое значение: {file_path}")
    return value


def read_redis_dsn() -> str | None:
    value = str(os.environ.get("GENOMEAI_REDIS_DSN", "") or "").strip()
    if value:
        return value
    host = str(os.environ.get("GENOMEAI_REDIS_HOST", "") or "").strip()
    if not host:
        return None
    port = int(str(os.environ.get("GENOMEAI_REDIS_PORT", "6379") or "6379"))
    db = int(str(os.environ.get("GENOMEAI_REDIS_DB", "0") or "0"))
    return f"redis://{host}:{port}/{db}"


def redact_redis_dsn(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value)
    except Exception:
        return "***"
    username = parsed.username or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    db = parsed.path or ""
    if username:
        netloc = f"{username}:***@{host}{port}"
    elif parsed.password:
        netloc = f":***@{host}{port}"
    else:
        netloc = f"{host}{port}"
    return urlunsplit((parsed.scheme, netloc, db, parsed.query, parsed.fragment))


def resolve_queue_runtime_settings() -> QueueRuntimeSettings:
    profile = normalize_runtime_profile(os.environ.get("GENOMEAI_DEPLOY_PROFILE"))
    adult_mode = profile in ADULT_RUNTIME_PROFILES
    backend_default = "redis" if adult_mode else "sqlite"
    backend = str(os.environ.get("GENOMEAI_JOB_QUEUE_BACKEND") or backend_default).strip().lower() or backend_default
    if backend not in SUPPORTED_QUEUE_BACKENDS:
        raise QueueRuntimeConfigError(
            f"GENOMEAI_JOB_QUEUE_BACKEND должен быть одним из {sorted(SUPPORTED_QUEUE_BACKENDS)}, получено: {backend!r}"
        )
    redis_dsn = read_redis_dsn()
    redis_password = _read_secret(env_name="GENOMEAI_REDIS_PASSWORD") or None
    return QueueRuntimeSettings(
        profile=profile,
        backend=backend,
        adult_mode=adult_mode,
        compat_mode=not adult_mode,
        redis_dsn=redis_dsn,
        redis_password=redis_password,
        key_prefix=str(os.environ.get("GENOMEAI_QUEUE_KEY_PREFIX") or DEFAULT_QUEUE_KEY_PREFIX).strip() or DEFAULT_QUEUE_KEY_PREFIX,
        visibility_timeout_sec=max(30, int(str(os.environ.get("GENOMEAI_QUEUE_VISIBILITY_TIMEOUT_SEC", "300") or "300"))),
        idempotency_ttl_sec=max(60, int(str(os.environ.get("GENOMEAI_QUEUE_IDEMPOTENCY_TTL_SEC", "86400") or "86400"))),
        claim_block_timeout_sec=max(1, int(str(os.environ.get("GENOMEAI_QUEUE_CLAIM_BLOCK_TIMEOUT_SEC", "1") or "1"))),
    )


def queue_runtime_diagnostics(settings: QueueRuntimeSettings | None = None) -> QueueRuntimeDiagnostics:
    cfg = settings or resolve_queue_runtime_settings()
    if cfg.backend == "redis":
        if not cfg.redis_dsn:
            broker_status = "blocked_missing_redis_dsn"
        else:
            broker_status = "redis_runtime_configured"
    else:
        broker_status = "sqlite_compat_queue_runtime"
    return QueueRuntimeDiagnostics(
        profile=cfg.profile,
        backend=cfg.backend,
        adult_mode=cfg.adult_mode,
        compat_mode=cfg.compat_mode,
        embedded_worker_allowed=(cfg.backend == "sqlite"),
        dedicated_worker_required=(cfg.backend == "redis"),
        redis_dsn_present=bool(cfg.redis_dsn),
        redis_dsn_redacted=redact_redis_dsn(cfg.redis_dsn),
        broker_status=broker_status,
        key_prefix=cfg.key_prefix,
        visibility_timeout_sec=int(cfg.visibility_timeout_sec),
        idempotency_ttl_sec=int(cfg.idempotency_ttl_sec),
        claim_block_timeout_sec=int(cfg.claim_block_timeout_sec),
    )


def validate_queue_runtime_settings(settings: QueueRuntimeSettings | None = None) -> QueueRuntimeDiagnostics:
    cfg = settings or resolve_queue_runtime_settings()
    diag = queue_runtime_diagnostics(cfg)
    if cfg.adult_mode and cfg.backend != "redis":
        raise QueueRuntimeConfigError("adult/stage/prod profile требует GENOMEAI_JOB_QUEUE_BACKEND=redis; embedded/sqlite queue path запрещён")
    if cfg.backend == "redis" and not cfg.redis_dsn:
        raise QueueRuntimeConfigError("Для redis queue runtime обязателен GENOMEAI_REDIS_DSN или GENOMEAI_REDIS_HOST/PORT/DB")
    return diag


class RedisWireClient:
    def __init__(self, *, dsn: str, password: str | None = None, timeout_sec: float = 5.0):
        self.dsn = str(dsn or "").strip()
        if not self.dsn:
            raise QueueRuntimeConfigError("RedisWireClient requires redis DSN")
        parsed = urlsplit(self.dsn)
        self.scheme = parsed.scheme or "redis"
        self.host = parsed.hostname or "127.0.0.1"
        self.port = int(parsed.port or 6379)
        self.db = int((parsed.path or "/0").strip("/") or "0")
        self.password = password or (parsed.password or None)
        self.timeout_sec = float(timeout_sec)

    def _connect(self) -> socket.socket:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout_sec)
        sock.settimeout(self.timeout_sec)
        if self.password:
            self.execute("AUTH", self.password, _sock=sock)
        if self.db:
            self.execute("SELECT", str(self.db), _sock=sock)
        return sock

    def _encode(self, *parts: Any) -> bytes:
        chunks = [f"*{len(parts)}\r\n".encode("utf-8")]
        for part in parts:
            if isinstance(part, bytes):
                raw = part
            else:
                raw = str(part).encode("utf-8")
            chunks.append(f"${len(raw)}\r\n".encode("utf-8"))
            chunks.append(raw + b"\r\n")
        return b"".join(chunks)

    def _read_line(self, sock: socket.socket) -> bytes:
        buf = bytearray()
        while True:
            ch = sock.recv(1)
            if not ch:
                raise ConnectionError("redis connection closed")
            buf.extend(ch)
            if len(buf) >= 2 and buf[-2:] == b"\r\n":
                return bytes(buf[:-2])

    def _read_reply(self, sock: socket.socket) -> Any:
        prefix = sock.recv(1)
        if not prefix:
            raise ConnectionError("redis connection closed")
        if prefix == b"+":
            return self._read_line(sock).decode("utf-8")
        if prefix == b"-":
            raise RuntimeError(self._read_line(sock).decode("utf-8"))
        if prefix == b":":
            return int(self._read_line(sock).decode("utf-8"))
        if prefix == b"$":
            size = int(self._read_line(sock).decode("utf-8"))
            if size == -1:
                return None
            data = bytearray()
            while len(data) < size + 2:
                chunk = sock.recv(size + 2 - len(data))
                if not chunk:
                    raise ConnectionError("redis bulk reply truncated")
                data.extend(chunk)
            return bytes(data[:-2]).decode("utf-8")
        if prefix == b"*":
            count = int(self._read_line(sock).decode("utf-8"))
            if count == -1:
                return None
            return [self._read_reply(sock) for _ in range(count)]
        raise RuntimeError(f"unsupported redis reply prefix: {prefix!r}")

    def execute(self, *parts: Any, _sock: socket.socket | None = None) -> Any:
        owned = _sock is None
        sock = _sock or self._connect()
        try:
            sock.sendall(self._encode(*parts))
            return self._read_reply(sock)
        finally:
            if owned:
                try:
                    sock.close()
                except Exception:
                    pass


class RedisQueueBroker:
    backend = "redis"

    def __init__(self, *, settings: QueueRuntimeSettings, client: Any | None = None):
        self.settings = settings
        self._client = client or RedisWireClient(dsn=str(settings.redis_dsn or ""), password=settings.redis_password)

    def _k(self, queue_name: str, suffix: str) -> str:
        q = str(queue_name or "default").strip() or "default"
        return f"{self.settings.key_prefix}:{q}:{suffix}"

    def _stats_key(self, queue_name: str) -> str:
        return self._k(queue_name, "stats")

    def ping(self) -> bool:
        try:
            return str(self._client.execute("PING") or "").upper() == "PONG"
        except Exception:
            return False

    def enqueue(self, envelope: QueueEnvelope, *, idempotency_key: str | None = None) -> dict[str, Any]:
        payload = envelope.raw_payload or envelope.serialize()
        idem = idempotency_key or f"job:{envelope.public_job_id}"
        enqueue_token_key = self._k(envelope.queue_name, f"idempotency:{idem}")
        queued = str(self._client.execute("SET", enqueue_token_key, envelope.public_job_id, "EX", str(self.settings.idempotency_ttl_sec), "NX") or "")
        if queued != "OK":
            return {"enqueued": False, "reason": "duplicate_idempotency_key", "idempotency_key": idem}
        self._client.execute("RPUSH", self._k(envelope.queue_name, "pending"), payload)
        self._client.execute("HINCRBY", self._stats_key(envelope.queue_name), "enqueued_total", "1")
        return {"enqueued": True, "reason": "queued", "idempotency_key": idem}

    def claim(self, *, queue_name: str, worker_id: str) -> QueueEnvelope | None:
        payload = self._client.execute(
            "BRPOPLPUSH",
            self._k(queue_name, "pending"),
            self._k(queue_name, "processing"),
            str(self.settings.claim_block_timeout_sec),
        )
        if payload is None:
            return None
        envelope = QueueEnvelope.from_payload(str(payload))
        now = utcnow_iso()
        inflight = {
            "job_id": envelope.job_id,
            "public_job_id": envelope.public_job_id,
            "worker_id": str(worker_id),
            "claimed_at": now,
            "heartbeat_at": now,
            "queue_name": envelope.queue_name,
            "attempt_no": envelope.attempt_no,
            "kind": envelope.kind,
        }
        self._client.execute("HSET", self._k(queue_name, "inflight"), envelope.public_job_id, json.dumps(inflight, ensure_ascii=False, sort_keys=True))
        self._client.execute("HINCRBY", self._stats_key(queue_name), "claimed_total", "1")
        return QueueEnvelope.from_payload(str(payload))

    def heartbeat(self, envelope: QueueEnvelope, *, worker_id: str) -> None:
        payload = self._client.execute("HGET", self._k(envelope.queue_name, "inflight"), envelope.public_job_id)
        if not payload:
            return
        current = json.loads(str(payload))
        current["worker_id"] = str(worker_id)
        current["heartbeat_at"] = utcnow_iso()
        self._client.execute("HSET", self._k(envelope.queue_name, "inflight"), envelope.public_job_id, json.dumps(current, ensure_ascii=False, sort_keys=True))

    def ack(self, envelope: QueueEnvelope, *, worker_id: str) -> None:
        payload = envelope.raw_payload or envelope.serialize()
        self._client.execute("LREM", self._k(envelope.queue_name, "processing"), "1", payload)
        self._client.execute("HDEL", self._k(envelope.queue_name, "inflight"), envelope.public_job_id)
        self._client.execute("HINCRBY", self._stats_key(envelope.queue_name), "acked_total", "1")

    def fail(self, envelope: QueueEnvelope, *, worker_id: str, reason: str, final_status: str = "failed") -> None:
        payload = envelope.raw_payload or envelope.serialize()
        self._client.execute("LREM", self._k(envelope.queue_name, "processing"), "1", payload)
        self._client.execute("HDEL", self._k(envelope.queue_name, "inflight"), envelope.public_job_id)
        record = {
            "job_id": envelope.job_id,
            "public_job_id": envelope.public_job_id,
            "queue_name": envelope.queue_name,
            "worker_id": str(worker_id),
            "failed_at": utcnow_iso(),
            "reason": str(reason or "failed"),
            "final_status": str(final_status or "failed"),
            "attempt_no": envelope.attempt_no,
            "max_attempts": envelope.max_attempts,
        }
        self._client.execute("LPUSH", self._k(envelope.queue_name, "deadletter"), json.dumps(record, ensure_ascii=False, sort_keys=True))
        self._client.execute("HINCRBY", self._stats_key(envelope.queue_name), "failed_total", "1")

    def note_retry(self, queue_name: str) -> None:
        self._client.execute("HINCRBY", self._stats_key(queue_name), "retried_total", "1")

    def queue_metrics(self, queue_name: str) -> dict[str, Any]:
        pending = int(self._client.execute("LLEN", self._k(queue_name, "pending")) or 0)
        processing = int(self._client.execute("LLEN", self._k(queue_name, "processing")) or 0)
        deadletter = int(self._client.execute("LLEN", self._k(queue_name, "deadletter")) or 0)
        inflight_raw = self._client.execute("HGETALL", self._k(queue_name, "inflight")) or []
        stats_raw = self._client.execute("HGETALL", self._stats_key(queue_name)) or []
        inflight: list[dict[str, Any]] = []
        if isinstance(inflight_raw, list):
            it = iter(inflight_raw)
            for key in it:
                try:
                    val = next(it)
                except StopIteration:
                    break
                try:
                    payload = json.loads(str(val))
                except Exception:
                    payload = {"public_job_id": str(key), "raw": str(val)}
                inflight.append(payload)
        stats: dict[str, int] = {}
        if isinstance(stats_raw, list):
            it = iter(stats_raw)
            for key in it:
                try:
                    val = next(it)
                except StopIteration:
                    break
                try:
                    stats[str(key)] = int(val)
                except Exception:
                    continue
        threshold = datetime.now(timezone.utc) - timedelta(seconds=int(self.settings.visibility_timeout_sec))
        stuck: list[dict[str, Any]] = []
        for item in inflight:
            hb = str(item.get("heartbeat_at") or item.get("claimed_at") or "").strip()
            try:
                hb_ts = datetime.fromisoformat(hb.replace("Z", "+00:00"))
            except Exception:
                hb_ts = None
            if hb_ts is not None and hb_ts < threshold:
                stuck.append(item)
        return {
            "queue_name": str(queue_name),
            "pending_jobs": pending,
            "inflight_jobs": processing,
            "deadletter_jobs": deadletter,
            "inflight": inflight,
            "stuck_jobs": stuck,
            "stats": stats,
            "worker_ids": sorted({str(item.get('worker_id') or '') for item in inflight if str(item.get('worker_id') or '')}),
        }


class SqliteCompatQueueBroker:
    backend = "sqlite"

    def __init__(self, *, settings: QueueRuntimeSettings):
        self.settings = settings

    def ping(self) -> bool:
        return True

    def enqueue(self, envelope: QueueEnvelope, *, idempotency_key: str | None = None) -> dict[str, Any]:
        return {"enqueued": True, "reason": "sqlite_compat_queue"}

    def claim(self, *, queue_name: str, worker_id: str) -> QueueEnvelope | None:
        return None

    def heartbeat(self, envelope: QueueEnvelope, *, worker_id: str) -> None:
        return None

    def ack(self, envelope: QueueEnvelope, *, worker_id: str) -> None:
        return None

    def fail(self, envelope: QueueEnvelope, *, worker_id: str, reason: str, final_status: str = "failed") -> None:
        return None

    def note_retry(self, queue_name: str) -> None:
        return None

    def queue_metrics(self, queue_name: str) -> dict[str, Any]:
        return {
            "queue_name": str(queue_name),
            "pending_jobs": None,
            "inflight_jobs": None,
            "deadletter_jobs": None,
            "inflight": [],
            "stuck_jobs": [],
            "stats": {},
            "worker_ids": [],
        }


_BROKER_FACTORY: Callable[[], Any] | None = None


def set_queue_broker_factory(factory: Callable[[], Any] | None) -> None:
    global _BROKER_FACTORY
    _BROKER_FACTORY = factory


def resolve_queue_runtime_broker() -> Any:
    if _BROKER_FACTORY is not None:
        return _BROKER_FACTORY()
    cfg = resolve_queue_runtime_settings()
    if cfg.backend == "redis":
        return RedisQueueBroker(settings=cfg)
    return SqliteCompatQueueBroker(settings=cfg)


def build_queue_runtime_summary_payload(*, queue_names: list[str] | None = None) -> dict[str, Any]:
    cfg = resolve_queue_runtime_settings()
    diag = queue_runtime_diagnostics(cfg).as_dict()
    names = [str(x).strip() or "default" for x in (queue_names or ["default"])]
    try:
        broker = resolve_queue_runtime_broker()
        queues = [broker.queue_metrics(name) for name in names]
        diag["queues"] = queues
        diag["broker_ping"] = bool(getattr(broker, "ping", lambda: False)())
    except Exception as exc:
        diag["queues"] = [{
            "queue_name": name,
            "pending_jobs": None,
            "inflight_jobs": None,
            "deadletter_jobs": None,
            "inflight": [],
            "stuck_jobs": [],
            "stats": {},
            "worker_ids": [],
        } for name in names]
        diag["broker_ping"] = False
        diag["broker_error"] = f"{type(exc).__name__}: {exc}"
    return diag


__all__ = [
    "QueueRuntimeConfigError",
    "QueueRuntimeSettings",
    "QueueRuntimeDiagnostics",
    "QueueEnvelope",
    "SUPPORTED_QUEUE_BACKENDS",
    "resolve_queue_runtime_settings",
    "queue_runtime_diagnostics",
    "validate_queue_runtime_settings",
    "RedisWireClient",
    "RedisQueueBroker",
    "SqliteCompatQueueBroker",
    "resolve_queue_runtime_broker",
    "build_queue_runtime_summary_payload",
    "set_queue_broker_factory",
]
