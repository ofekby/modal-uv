# Modal-UV Connection Daemon Design

**Date:** 2026-06-06
**Status:** Approved
**Scope:** Add persistent local daemon for Modal client connection reuse.

## Problem

Each `modal-uv` invocation starts a fresh Python process via `uv run`, loads the Modal client, and establishes a gRPC connection to Modal. This costs ~1.15s per invocation, regardless of the actual API call time (~0.3s). Over 5 sequential runs, this adds ~5.75s of pure startup overhead.

## Goals

- Eliminate per-invocation Modal client connection setup.
- Maintain a persistent local daemon that holds the Modal `Worker` handle.
- CLI commands connect to the daemon via Unix domain socket.
- Daemon auto-shuts down after idle timeout.
- Daemon does not affect Modal container scaling (daemon is local-only).

## Non-Goals

- No changes to Modal container behavior or `scaledown_window`.
- No daemon on Modal — the daemon runs on the local machine only.
- No persistent gRPC connection to Modal containers — the daemon uses the same Modal Python client as before.

## Architecture

```text
modal-uv py -- -m lab
    │
    ├─ build manifest locally
    │
    ├─ connect to daemon (spawn if needed)
    │      │
    │      ├─ daemon: plan_sync.remote(manifest) → missing paths
    │      │
    │      └─ daemon: reads missing files from disk, builds payloads,
    │                 sync_and_run_python.spawn(...) → execution_id
    │
    └─ print execution_id, exit
```

The daemon is a local process. It does not run on Modal. Modal container scaling is controlled by `scaledown_window` in `deploy.py` and is unaffected by the daemon.

## Components

### 1. `modal_uv/daemon.py`

Daemon process:
- Listens on Unix domain socket at `.modal-uv-daemon.sock`
- Holds Modal `Worker` handle (connected once at startup)
- Accepts JSON requests, forwards to Modal, returns JSON responses
- Auto-shuts down after 5 minutes idle
- Cleans up socket and PID file on exit

### 2. `modal_uv/client.py`

Client helper:
- Checks `.modal-uv-daemon-pid` for running daemon
- If PID is alive and socket exists → connect
- If PID is dead or socket missing → spawn new daemon, wait for socket, connect
- Sends requests over socket, returns responses

### 3. Files

| File | Location | Purpose |
|---|---|---|
| `.modal-uv-daemon-pid` | repo root | Daemon process PID |
| `.modal-uv-daemon.sock` | repo root | Unix domain socket |

Both files are gitignored.

## Protocol

Newline-delimited JSON over Unix socket.

### Requests

File contents are NOT sent over the socket. The client sends only file paths. The daemon reads file contents from disk and sends them to Modal.

```json
{"action": "ping"}
{"action": "plan_sync", "manifest": [{"path": "src/app.py", "size": 100, "mtime_ns": 1700000000000000000}]}
{"action": "spawn", "manifest": [...], "missing_paths": ["src/app.py"], "args": ["python", "-m", "lab"]}
{"action": "spawn_python", "manifest": [...], "missing_paths": ["src/app.py"], "request": {"kind": "module", "target": "lab", "args": []}}
```

### Responses

```json
{"status": "ok", "result": "pong"}
{"status": "ok", "result": ["src/app.py"]}
{"status": "ok", "execution_id": "fc-..."}
{"status": "error", "message": "connection failed"}
```

## Daemon Lifecycle

### Startup

1. Write PID to `.modal-uv-daemon-pid`
2. Create Unix socket at `.modal-uv-daemon.sock`
3. Connect to Modal: `modal.Cls.from_name(app_name, "Worker")`
4. Start idle timer
5. Listen for requests

### Request Handling

1. Read JSON line from socket
2. Parse request
3. For `spawn`/`spawn_python`: read file contents from disk using `missing_paths`, build `FilePayload` list
4. Forward to Modal `Worker` method
5. Write JSON response line
6. Reset idle timer

### Shutdown

- Idle timeout: 5 minutes with no requests
- Explicit stop: `modal-uv daemon stop`
- Socket/PID cleanup on any exit

### Client Connection

1. Read `.modal-uv-daemon-pid`
2. Check PID is alive (`os.kill(pid, 0)`)
3. Check `.modal-uv-daemon.sock` exists
4. Connect to socket
5. If any check fails → spawn new daemon, wait for socket (up to 10s), connect

## CLI Commands

### `modal-uv run` / `modal-uv py`

Same as before, but route Modal calls through daemon.

### `modal-uv daemon stop`

Kill daemon, clean up PID/socket.

### `modal-uv daemon status`

Show daemon PID, uptime, socket path.

## Error Handling

- Daemon not starting → fall back to direct Modal calls
- Daemon dies mid-request → client retries once (spawn new daemon)
- Socket connection refused → spawn new daemon
- Invalid JSON response → error and exit

## Expected Performance

| Scenario | Time |
|---|---|
| Cold daemon (first call) | ~2s (daemon spawn + Modal connect + request) |
| Warm daemon (subsequent) | ~0.3s (API round-trip only) |

## Modal Container Scaling

The daemon is a local process. It does not run on Modal. It does not keep Modal containers warm. Modal container scaling is controlled by `scaledown_window=300` in `deploy.py` and is based on method invocations, not client connections.

## Testing

- Unit-test daemon request/response protocol
- Unit-test client daemon lifecycle (spawn, connect, reconnect)
- Unit-test idle timeout shutdown
- Unit-test daemon stop command
- Integration-test warm daemon latency ~0.3s
- Integration-test daemon auto-shutdown after idle
