"""Persistent daemon for Modal client connection reuse via FastAPI over Unix socket."""

from __future__ import annotations

import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from modal_uv.config import load_config
from modal_uv.deployment import ensure_deployment_current
from modal_uv.paths import ensure_repo_state
from modal_uv.sync import FilePayload, FileState, validate_relative_path


class PlanSyncRequest(BaseModel):
    manifest: list[dict]
    expected_fingerprint: str


class SpawnRequest(BaseModel):
    manifest: list[dict]
    missing_paths: list[str]
    args: list[str]
    mode: Literal["run", "exec"] = "run"


class DaemonResponse(BaseModel):
    status: str
    result: object = None
    execution_id: str | None = None
    message: str | None = None


_worker: Any = None
_repo_root: Path | None = None
_app_name: str = ""
_last_activity: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _last_activity
    _last_activity = time.monotonic()
    yield


app = FastAPI(title="modal-uv daemon", lifespan=lifespan)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": str(exc)},
    )


@app.get("/ping")
def ping() -> DaemonResponse:
    global _last_activity
    _last_activity = time.monotonic()
    return DaemonResponse(status="ok", result="pong")


@app.post("/plan_sync")
def plan_sync(req: PlanSyncRequest) -> DaemonResponse:
    global _last_activity
    _last_activity = time.monotonic()

    try:
        remote_fp = _query_remote_fingerprint()
    except Exception:
        return DaemonResponse(status="restart_needed")
    if remote_fp != req.expected_fingerprint:
        return DaemonResponse(status="restart_needed")

    manifest = [FileState(**item) for item in req.manifest]
    result = _worker.plan_sync.remote(manifest)
    return DaemonResponse(status="ok", result=result)


@app.post("/spawn")
def spawn(req: SpawnRequest) -> DaemonResponse:
    global _last_activity
    _last_activity = time.monotonic()
    manifest = [FileState(**item) for item in req.manifest]
    payloads = _read_payloads(req.missing_paths, manifest)
    call = _worker.sync_and_run.spawn(manifest, payloads, req.args, req.mode)
    return DaemonResponse(status="ok", execution_id=call.object_id)


def _read_payloads(missing_paths: list[str], manifest: list[FileState]) -> list[FilePayload]:
    for item in manifest:
        validate_relative_path(item.path)
    state_by_path = {item.path: item for item in manifest}
    payloads: list[FilePayload] = []
    for rel_path in missing_paths:
        source = _safe_repo_path(rel_path)
        state = state_by_path[rel_path]
        if not source.exists():
            raise FileNotFoundError(f"missing upload file: {rel_path}")
        payloads.append(
            FilePayload(
                path=rel_path,
                size=state.size,
                mtime_ns=state.mtime_ns,
                content=source.read_bytes(),
                mode=state.mode,
            )
        )
    return payloads


def _safe_repo_path(relative_path: str) -> Path:
    validate_relative_path(relative_path)
    if _repo_root is None:
        raise RuntimeError("daemon repo root is not initialized")

    repo_root = os.path.realpath(_repo_root)
    source = os.path.realpath(os.path.join(repo_root, relative_path))
    if os.path.commonpath([repo_root, source]) != repo_root:
        raise ValueError(f"unsafe path: {relative_path}")
    return Path(source)


def _query_remote_fingerprint() -> str:
    """Query the deployed app's fingerprint from the remote container."""
    from modal_uv.deployment import query_deployed_fingerprint

    return query_deployed_fingerprint(_app_name)


def run_daemon_entry(config_path: Path, repo_root: Path) -> None:
    """Entry point for daemon subprocess."""
    import modal

    from modal_uv.paths import daemon_paths

    global _worker, _repo_root, _app_name

    config = load_config(config_path)
    ensure_repo_state(repo_root)
    pid_path, sock_path = daemon_paths(repo_root)
    _repo_root = repo_root
    _app_name = config.app_name

    if sock_path.exists():
        sock_path.unlink()

    pid_path.write_text(str(os.getpid()))

    ensure_deployment_current(config, repo_root)
    _worker = modal.Cls.from_name(config.app_name, "Worker")()

    print(f"[daemon] started pid={os.getpid()} sock={sock_path}", flush=True)

    config = uvicorn.Config(
        app,
        uds=str(sock_path),
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()

    pid_path.unlink(missing_ok=True)
    sock_path.unlink(missing_ok=True)
    print("[daemon] shut down", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python -m modal_uv.daemon <config_path> <repo_root>", file=sys.stderr)
        sys.exit(1)
    run_daemon_entry(Path(sys.argv[1]), Path(sys.argv[2]))
