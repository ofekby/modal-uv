"""Tests for modal-uv app definition."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from modal_uv import __version__
from modal_uv.app import create_app


def _make_config() -> dict[str, Any]:
    return {
        "app_name": "test-app",
        "gpu": "T4",
        "cpu": 2.0,
        "memory": 2048,
        "volumes": [
            {"name": "test-volume", "mount_path": "/mnt/volume", "commit_interval_seconds": 45},
        ],
        "env": {},
        "work_dir": "/tmp/work",
        "image_base": "python:3.12-slim",
        "scaledown_window_seconds": 120,
        "runtime_exec": None,
        "fingerprint": "abc123",
    }


def _setup_mocks(mock_modal: MagicMock) -> MagicMock:
    mock_app = MagicMock()
    mock_modal.App.return_value = mock_app
    mock_modal.Volume.from_name.return_value = MagicMock()
    image_mock = MagicMock()
    image_chain = mock_modal.Image.from_registry.return_value
    env_result = MagicMock()
    env_result.add_local_python_source.return_value = image_mock
    run_commands = image_chain.apt_install.return_value.run_commands.return_value
    run_commands.pip_install.return_value.env.return_value = env_result
    return mock_app


class _PassthroughImage:
    def apt_install(self, *_args: str) -> _PassthroughImage:
        return self

    def run_commands(self, *_args: str) -> _PassthroughImage:
        return self

    def pip_install(self, *_args: str) -> _PassthroughImage:
        return self

    def env(self, _env: dict[str, str]) -> _PassthroughImage:
        return self

    def add_local_python_source(self, *_args: str) -> _PassthroughImage:
        return self


class _CapturingApp:
    worker_cls: type | None = None

    def function(self, **_kwargs: Any):
        def decorator(fn):
            return fn

        return decorator

    def cls(self, **_kwargs: Any):
        def decorator(cls):
            self.worker_cls = cls
            return cls

        return decorator


def _create_worker(tmp_path: Path, *, runtime_exec: str | None = None):
    capturing_app = _CapturingApp()
    fake_modal = MagicMock()
    fake_modal.App.return_value = capturing_app
    fake_modal.Image.from_registry.return_value = _PassthroughImage()
    fake_modal.Volume.from_name.return_value = MagicMock()
    fake_modal.concurrent.return_value = lambda cls: cls
    fake_modal.method.return_value = lambda fn: fn
    config = _make_config()
    config["work_dir"] = str(tmp_path / "remote")
    config["volumes"] = []
    config["runtime_exec"] = runtime_exec
    with patch("modal_uv.app.modal", fake_modal):
        create_app(**config)
    assert capturing_app.worker_cls is not None
    return capturing_app.worker_cls()


@patch("modal_uv.app.modal")
def test_create_app_returns_app(mock_modal: MagicMock) -> None:
    mock_app = _setup_mocks(mock_modal)

    result = create_app(**_make_config())

    mock_modal.App.assert_called_once_with(name="test-app")
    assert result is mock_app


@patch("modal_uv.app.modal")
def test_create_app_does_not_create_s3_mount(mock_modal: MagicMock) -> None:
    _setup_mocks(mock_modal)

    create_app(**_make_config())

    mock_modal.CloudBucketMount.assert_not_called()
    mock_modal.Secret.from_name.assert_not_called()


@patch("modal_uv.app.modal")
def test_create_app_uses_volume_name(mock_modal: MagicMock) -> None:
    _setup_mocks(mock_modal)

    create_app(**_make_config())

    mock_modal.Volume.from_name.assert_called_once_with(
        "test-volume",
        create_if_missing=True,
    )


@patch("modal_uv.app.modal")
def test_create_app_configures_uv_to_use_system_environment(mock_modal: MagicMock) -> None:
    _setup_mocks(mock_modal)

    create_app(**_make_config())

    run_commands = mock_modal.Image.from_registry.return_value.apt_install.return_value.run_commands
    env_call = run_commands.return_value.pip_install.return_value.env
    env_call.assert_called_once()
    assert env_call.call_args.args[0]["UV_PROJECT_ENVIRONMENT"] == "/usr/local"
    assert env_call.call_args.args[0]["MODAL_UV_VERSION"] == __version__


@patch("modal_uv.app.modal")
def test_create_app_limits_worker_to_one_container(mock_modal: MagicMock) -> None:
    mock_app = _setup_mocks(mock_modal)

    create_app(**_make_config())

    cls_kwargs = mock_app.cls.call_args.kwargs
    assert cls_kwargs["max_containers"] == 1


@patch("modal_uv.app.modal")
def test_create_app_uses_scaledown_window(mock_modal: MagicMock) -> None:
    mock_app = _setup_mocks(mock_modal)

    create_app(**_make_config())

    cls_kwargs = mock_app.cls.call_args.kwargs
    assert cls_kwargs["scaledown_window"] == 120


@patch("modal_uv.app.modal")
def test_create_app_passes_runtime_resources_to_worker(mock_modal: MagicMock) -> None:
    mock_app = _setup_mocks(mock_modal)

    create_app(**_make_config())

    cls_kwargs = mock_app.cls.call_args.kwargs
    assert cls_kwargs["gpu"] == "T4"
    assert cls_kwargs["cpu"] == 2.0
    assert cls_kwargs["memory"] == 2048


@patch("modal_uv.app.modal")
def test_create_app_omits_gpu_when_not_configured(mock_modal: MagicMock) -> None:
    mock_app = _setup_mocks(mock_modal)

    config = _make_config()
    config["gpu"] = None
    create_app(**config)

    cls_kwargs = mock_app.cls.call_args.kwargs
    assert "gpu" not in cls_kwargs


@patch("modal_uv.app.modal")
def test_create_app_registers_deployment_fingerprint_on_custom_image(mock_modal: MagicMock) -> None:
    mock_app = _setup_mocks(mock_modal)

    create_app(**_make_config())

    func_kwargs = mock_app.function.call_args.kwargs
    from_reg = mock_modal.Image.from_registry.return_value
    chain = from_reg.apt_install.return_value.run_commands.return_value
    chain = chain.pip_install.return_value.env.return_value
    assert func_kwargs["image"] is chain.add_local_python_source.return_value
    assert func_kwargs["serialized"] is True


@patch("modal_uv.app.modal")
def test_create_app_registers_deployment_fingerprint_function(mock_modal: MagicMock) -> None:
    mock_app = _setup_mocks(mock_modal)

    create_app(**_make_config())

    assert mock_app.function.called


@patch("modal_uv.app.modal")
def test_create_app_passes_volumes_to_worker(mock_modal: MagicMock) -> None:
    mock_app = _setup_mocks(mock_modal)

    config = _make_config()
    config["volumes"] = [
        {"name": "vol-a", "mount_path": "/mnt/a", "commit_interval_seconds": 30},
        {"name": "vol-b", "mount_path": "/mnt/b", "commit_interval_seconds": 60},
    ]
    create_app(**config)

    cls_kwargs = mock_app.cls.call_args.kwargs
    assert "/mnt/a" in cls_kwargs["volumes"]
    assert "/mnt/b" in cls_kwargs["volumes"]


@patch("modal_uv.app.modal")
def test_create_app_no_volumes_omits_volumes_kwarg(mock_modal: MagicMock) -> None:
    mock_app = _setup_mocks(mock_modal)

    config = _make_config()
    config["volumes"] = []
    create_app(**config)

    cls_kwargs = mock_app.cls.call_args.kwargs
    assert "volumes" not in cls_kwargs


@patch("modal_uv.app.modal")
def test_create_app_merges_user_env_over_infra_defaults(mock_modal: MagicMock) -> None:
    _setup_mocks(mock_modal)

    config = _make_config()
    config["env"] = {"MY_KEY": "val", "UV_PROJECT_ENVIRONMENT": "/custom"}
    create_app(**config)

    run_commands = mock_modal.Image.from_registry.return_value.apt_install.return_value.run_commands
    env_call = run_commands.return_value.pip_install.return_value.env
    env_dict = env_call.call_args.args[0]
    assert env_dict["MY_KEY"] == "val"
    assert env_dict["UV_PROJECT_ENVIRONMENT"] == "/custom"
    assert env_dict["UV_LINK_MODE"] == "copy"


def test_worker_run_mode_uses_uv_run_command(tmp_path: Path) -> None:
    worker = _create_worker(tmp_path)

    with (
        patch("modal_uv.app.subprocess.run") as mock_run,
        patch("modal_uv.app.uv_run_command", return_value=["uv", "run", "pytest"]) as mock_uv_run,
    ):
        mock_run.return_value.returncode = 0
        result = worker.sync_and_run([], [], ["pytest"], "run")

    assert result == 0
    mock_uv_run.assert_called_once_with(["pytest"])
    mock_run.assert_called_once()
    assert mock_run.call_args.args[0] == ["uv", "run", "pytest"]


def test_worker_exec_mode_uses_configured_shell_without_uv(tmp_path: Path) -> None:
    worker = _create_worker(tmp_path, runtime_exec="bash")

    with (
        patch("modal_uv.app.subprocess.run") as mock_run,
        patch("modal_uv.app.uv_run_command") as mock_uv_run,
    ):
        mock_run.return_value.returncode = 0
        result = worker.sync_and_run([], [], ["echo hi"], "exec")

    assert result == 0
    mock_uv_run.assert_not_called()
    assert mock_run.call_args.args[0] == ["bash", "-c", "echo hi"]


def test_worker_exec_mode_falls_back_to_remote_shell_env(tmp_path: Path) -> None:
    worker = _create_worker(tmp_path)

    with (
        patch.dict("modal_uv.app.os.environ", {"SHELL": "/bin/zsh"}, clear=False),
        patch("modal_uv.app.subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0
        worker.sync_and_run([], [], ["pwd"], "exec")

    assert mock_run.call_args.args[0] == ["/bin/zsh", "-c", "pwd"]


def test_worker_exec_mode_falls_back_to_bin_sh(tmp_path: Path) -> None:
    worker = _create_worker(tmp_path)

    with (
        patch.dict("modal_uv.app.os.environ", {}, clear=True),
        patch("modal_uv.app.subprocess.run") as mock_run,
    ):
        mock_run.return_value.returncode = 0
        worker.sync_and_run([], [], ["pwd"], "exec")

    assert mock_run.call_args.args[0] == ["/bin/sh", "-c", "pwd"]


def test_worker_rejects_unknown_execution_mode(tmp_path: Path) -> None:
    worker = _create_worker(tmp_path)

    with pytest.raises(ValueError, match="unknown execution mode"):
        worker.sync_and_run([], [], [], "invalid")


def test_worker_exec_mode_rejects_empty_command(tmp_path: Path) -> None:
    worker = _create_worker(tmp_path)

    with pytest.raises(ValueError, match="exec command is required"):
        worker.sync_and_run([], [], [], "exec")
