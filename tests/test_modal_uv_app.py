"""Tests for modal-uv app definition."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from modal_uv.app import create_app


def _make_config() -> dict[str, Any]:
    return {
        "app_name": "test-app",
        "gpu": "T4",
        "volumes": [
            {"name": "test-volume", "mount_path": "/mnt/volume", "commit_interval_seconds": 45},
        ],
        "env": {},
        "work_dir": "/tmp/work",
        "image_base": "python:3.12-slim",
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


@patch("modal_uv.app.modal")
def test_create_app_limits_worker_to_one_container(mock_modal: MagicMock) -> None:
    mock_app = _setup_mocks(mock_modal)

    create_app(**_make_config())

    cls_kwargs = mock_app.cls.call_args.kwargs
    assert cls_kwargs["max_containers"] == 1


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
