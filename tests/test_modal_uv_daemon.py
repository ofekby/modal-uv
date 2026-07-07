"""Tests for modal-uv daemon and client."""

from __future__ import annotations

import sys
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from modal_uv.daemon import _read_payloads, app
from modal_uv.sync import FileState


def _write_manifest_file(tmp_path: Path, rel: str, content: str) -> FileState:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    stat = p.stat()
    return FileState(path=rel, size=stat.st_size, mtime_ns=stat.st_mtime_ns)


def _setup_daemon(tmp_path: Path, worker: MagicMock) -> None:
    import modal_uv.daemon as d

    d._worker = worker
    d._repo_root = tmp_path


def _write_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "modal-uv.yaml"
    path.write_text(
        dedent(
            """\
            app_name: "test-app"
            volume:
              name: "test-volume"
            """
        ),
        encoding="utf-8",
    )
    return path


def test_ping() -> None:
    client = TestClient(app)
    resp = client.get("/ping")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["result"] == "pong"


@patch("modal_uv.daemon.uvicorn.Server")
@patch("modal_uv.daemon.uvicorn.Config")
@patch("modal_uv.daemon.ensure_deployment_current")
def test_run_daemon_entry_ensures_deployment_before_worker_lookup(
    mock_ensure_deployment: MagicMock,
    mock_uvicorn_config: MagicMock,
    mock_uvicorn_server: MagicMock,
    tmp_path: Path,
) -> None:
    import modal_uv.daemon as d

    events: list[str] = []
    config_path = _write_yaml(tmp_path)
    fake_modal = MagicMock()
    fake_worker_factory = MagicMock(return_value=MagicMock())
    fake_modal.Cls.from_name.side_effect = lambda app_name, class_name: (
        events.append("worker_lookup") or fake_worker_factory
    )
    mock_ensure_deployment.side_effect = lambda config, repo_root: events.append("deploy")
    mock_uvicorn_server.return_value.run.return_value = None

    with patch.dict(sys.modules, {"modal": fake_modal}):
        d.run_daemon_entry(config_path, tmp_path)

    assert events == ["deploy", "worker_lookup"]
    mock_ensure_deployment.assert_called_once()
    fake_modal.Cls.from_name.assert_called_once_with("test-app", "Worker")
    mock_uvicorn_config.assert_called_once()


def test_plan_sync(tmp_path: Path) -> None:
    worker = MagicMock()
    worker.plan_sync.remote.return_value = ["src/app.py"]
    _setup_daemon(tmp_path, worker)

    client = TestClient(app)
    with patch("modal_uv.daemon._query_remote_fingerprint", return_value="expected-fp"):
        resp = client.post(
            "/plan_sync",
            json={
                "manifest": [{"path": "src/app.py", "size": 10, "mtime_ns": 100}],
                "expected_fingerprint": "expected-fp",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["result"] == ["src/app.py"]
    worker.plan_sync.remote.assert_called_once()


def test_plan_sync_with_matching_fingerprint_proceeds(tmp_path: Path) -> None:
    worker = MagicMock()
    worker.plan_sync.remote.return_value = []
    _setup_daemon(tmp_path, worker)

    client = TestClient(app)
    with patch("modal_uv.daemon._query_remote_fingerprint", return_value="expected-fp"):
        resp = client.post(
            "/plan_sync",
            json={
                "manifest": [],
                "expected_fingerprint": "expected-fp",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    worker.plan_sync.remote.assert_called_once()


def test_plan_sync_with_mismatched_fingerprint_returns_restart_needed(tmp_path: Path) -> None:
    worker = MagicMock()
    _setup_daemon(tmp_path, worker)

    client = TestClient(app)
    with patch("modal_uv.daemon._query_remote_fingerprint", return_value="stale-fp"):
        resp = client.post(
            "/plan_sync",
            json={
                "manifest": [],
                "expected_fingerprint": "expected-fp",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "restart_needed"
    worker.plan_sync.remote.assert_not_called()


def test_plan_sync_fingerprint_check_treats_missing_as_restart_needed(tmp_path: Path) -> None:
    worker = MagicMock()
    _setup_daemon(tmp_path, worker)

    client = TestClient(app)
    with patch(
        "modal_uv.daemon._query_remote_fingerprint",
        side_effect=Exception("connection refused"),
    ):
        resp = client.post(
            "/plan_sync",
            json={"manifest": [], "expected_fingerprint": "expected-fp"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "restart_needed"


def test_plan_sync_returns_error_on_failure(tmp_path: Path) -> None:
    worker = MagicMock()
    worker.plan_sync.remote.side_effect = RuntimeError("modal down")
    _setup_daemon(tmp_path, worker)

    client = TestClient(app, raise_server_exceptions=False)
    with patch("modal_uv.daemon._query_remote_fingerprint", return_value="expected-fp"):
        resp = client.post(
            "/plan_sync",
            json={"manifest": [], "expected_fingerprint": "expected-fp"},
        )
    assert resp.status_code == 500
    data = resp.json()
    assert data["status"] == "error"
    assert "modal down" in data["message"]


def test_read_payloads(tmp_path: Path) -> None:
    fs = _write_manifest_file(tmp_path, "src/app.py", "content")
    import modal_uv.daemon as d

    d._repo_root = tmp_path
    payloads = _read_payloads(["src/app.py"], [fs])
    assert len(payloads) == 1
    assert payloads[0].content == b"content"


def test_read_payloads_rejects_missing_file(tmp_path: Path) -> None:
    fs = FileState(path="missing.py", size=1, mtime_ns=1)
    import modal_uv.daemon as d

    d._repo_root = tmp_path
    with pytest.raises(FileNotFoundError):
        _read_payloads(["missing.py"], [fs])
