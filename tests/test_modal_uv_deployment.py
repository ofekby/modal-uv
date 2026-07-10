from __future__ import annotations

import importlib.metadata
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from modal_uv.config import load_config
from modal_uv.deployment import (
    DeploymentBroken,
    DeploymentMissing,
    deployment_fingerprint,
    deployment_parameters,
    ensure_deployment_current,
    is_local_install,
    load_deployment_template,
    pyproject_sha256,
    query_deployed_fingerprint,
    render_deployment,
    write_deployment_artifact,
)


def _write_yaml(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "modal-uv.yaml"
    path.write_text(dedent(content), encoding="utf-8")
    return path


def _config(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        work_dir: "/tmp/work"
        volumes:
          - name: "test-volume"
            mount_path: "/mnt/volume"
            commit_interval_seconds: 45
        env:
          MY_KEY: "myval"
        runtime:
          gpu: "T4"
          cpu: 2
          memory: 2048
          scaledown_window_seconds: 120
        image:
          base_image: "python:3.12-slim"
        sync:
          ignore:
            - "data/**"
        """,
    )
    return load_config(path)


def _config_with_runtime_exec(tmp_path: Path):
    path = _write_yaml(
        tmp_path,
        """\
        app_name: "test-app"
        runtime:
          exec: "bash"
        """,
    )
    return load_config(path)


def test_deployment_parameters_exclude_sync_ignore(tmp_path: Path) -> None:
    params = deployment_parameters(_config(tmp_path))

    assert params == {
        "app_name": "test-app",
        "work_dir": "/tmp/work",
        "volumes": [
            {
                "name": "test-volume",
                "mount_path": "/mnt/volume",
                "commit_interval_seconds": 45,
            }
        ],
        "env": {"MY_KEY": "myval"},
        "runtime": {
            "gpu": "T4",
            "cpu": 2.0,
            "memory": 2048,
            "scaledown_window_seconds": 120,
            "exec": None,
        },
        "image": {"base_image": "python:3.12-slim", "add_python_version": None},
    }


def test_deployment_parameters_include_configured_runtime_exec(tmp_path: Path) -> None:
    params = deployment_parameters(_config_with_runtime_exec(tmp_path))

    assert params["runtime"]["exec"] == "bash"


def test_deployment_fingerprint_is_stable_for_identical_inputs(tmp_path: Path) -> None:
    config = _config(tmp_path)
    template = "template"

    first = deployment_fingerprint(template, deployment_parameters(config), tmp_path)
    second = deployment_fingerprint(template, deployment_parameters(config), tmp_path)

    assert first == second


def test_deployment_fingerprint_changes_when_template_changes(tmp_path: Path) -> None:
    config = _config(tmp_path)
    params = deployment_parameters(config)

    first = deployment_fingerprint("template-a", params, tmp_path)
    second = deployment_fingerprint("template-b", params, tmp_path)

    assert first != second


def test_deployment_fingerprint_changes_when_parameters_change(tmp_path: Path) -> None:
    config = _config(tmp_path)
    first_params = deployment_parameters(config)
    second_params = {
        **first_params,
        "runtime": {**first_params["runtime"], "gpu": "A100"},
    }

    first = deployment_fingerprint("template", first_params, tmp_path)
    second = deployment_fingerprint("template", second_params, tmp_path)

    assert first != second


def test_deployment_fingerprint_changes_when_runtime_exec_changes(tmp_path: Path) -> None:
    first_params = deployment_parameters(_config(tmp_path))
    second_params = {
        **first_params,
        "runtime": {**first_params["runtime"], "exec": "bash"},
    }

    first = deployment_fingerprint("template", first_params, tmp_path)
    second = deployment_fingerprint("template", second_params, tmp_path)

    assert first != second


def test_deployment_fingerprint_changes_when_pyproject_changes(tmp_path: Path) -> None:
    config = _config(tmp_path)
    params = deployment_parameters(config)
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'one'\n", encoding="utf-8")
    first = deployment_fingerprint("template", params, tmp_path)

    pyproject.write_text("[project]\nname = 'two'\n", encoding="utf-8")
    second = deployment_fingerprint("template", params, tmp_path)

    assert first != second


def test_deployment_fingerprint_changes_when_tool_versions_change(tmp_path: Path) -> None:
    config = _config(tmp_path)
    params = deployment_parameters(config)

    first = deployment_fingerprint(
        "template",
        params,
        tmp_path,
        tool_versions={"modal_uv": "1.0.0", "uv": "0.1.0", "modal": "1.4.3"},
    )
    second = deployment_fingerprint(
        "template",
        params,
        tmp_path,
        tool_versions={"modal_uv": "1.0.1", "uv": "0.1.0", "modal": "1.4.3"},
    )

    assert first != second


def test_deployment_fingerprint_changes_when_modal_uv_source_changes(tmp_path: Path) -> None:
    config = _config(tmp_path)
    params = deployment_parameters(config)

    first = deployment_fingerprint(
        "template",
        params,
        tmp_path,
        modal_uv_source_sha256="source-a",
    )
    second = deployment_fingerprint(
        "template",
        params,
        tmp_path,
        modal_uv_source_sha256="source-b",
    )

    assert first != second


def test_is_local_install_true_for_file_url() -> None:
    dist = MagicMock()
    dist.read_text.return_value = (
        '{"url":"file:///home/ofek/repos/modal-uv","dir_info":{"editable":true}}'
    )

    with patch("modal_uv.deployment.importlib.metadata.distribution", return_value=dist):
        assert is_local_install() is True


def test_is_local_install_false_for_pypi_url() -> None:
    dist = MagicMock()
    dist.read_text.return_value = '{"url":"https://files.pythonhosted.org/packages/..."}'

    with patch("modal_uv.deployment.importlib.metadata.distribution", return_value=dist):
        assert is_local_install() is False


def test_is_local_install_false_when_no_direct_url() -> None:
    dist = MagicMock()
    dist.read_text.return_value = None

    with patch("modal_uv.deployment.importlib.metadata.distribution", return_value=dist):
        assert is_local_install() is False


def test_is_local_install_true_when_package_missing() -> None:
    with patch(
        "modal_uv.deployment.importlib.metadata.distribution",
        side_effect=importlib.metadata.PackageNotFoundError,
    ):
        assert is_local_install() is True


@patch("modal_uv.deployment.is_local_install", return_value=False)
def test_fingerprint_excludes_source_hash_when_not_local(
    mock_local: MagicMock,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    params = deployment_parameters(config)

    first = deployment_fingerprint("template", params, tmp_path)
    second = deployment_fingerprint("template", params, tmp_path)

    assert first == second
    mock_local.assert_called()


def test_missing_pyproject_hash_is_deterministic(tmp_path: Path) -> None:
    assert pyproject_sha256(tmp_path) is None
    assert pyproject_sha256(tmp_path) is None


def test_render_deployment_is_deterministic(tmp_path: Path) -> None:
    config = _config(tmp_path)
    params = deployment_parameters(config)
    template = load_deployment_template()
    fingerprint = deployment_fingerprint(template, params, tmp_path)

    first = render_deployment(template, params, fingerprint)
    second = render_deployment(template, params, fingerprint)

    assert first == second


def test_render_deployment_embeds_fingerprint(tmp_path: Path) -> None:
    config = _config(tmp_path)
    params = deployment_parameters(config)
    template = load_deployment_template()
    fingerprint = deployment_fingerprint(template, params, tmp_path)

    rendered = render_deployment(template, params, fingerprint)

    assert fingerprint in rendered
    assert "fingerprint=" in rendered


def test_render_deployment_does_not_define_standalone_fingerprint_function(tmp_path: Path) -> None:
    config = _config(tmp_path)
    params = deployment_parameters(config)
    template = load_deployment_template()
    fingerprint = deployment_fingerprint(template, params, tmp_path)

    rendered = render_deployment(template, params, fingerprint)

    assert "@app.function" not in rendered


def test_render_deployment_embeds_volume_commit_interval(tmp_path: Path) -> None:
    config = _config(tmp_path)
    params = deployment_parameters(config)
    template = load_deployment_template()
    fingerprint = deployment_fingerprint(template, params, tmp_path)

    rendered = render_deployment(template, params, fingerprint)

    assert "commit_interval_seconds" in rendered
    assert "'test-volume'" in rendered


def test_render_deployment_embeds_scaledown_window(tmp_path: Path) -> None:
    config = _config(tmp_path)
    params = deployment_parameters(config)
    template = load_deployment_template()
    fingerprint = deployment_fingerprint(template, params, tmp_path)

    rendered = render_deployment(template, params, fingerprint)

    assert "scaledown_window_seconds=120" in rendered


def test_render_deployment_embeds_runtime_resources(tmp_path: Path) -> None:
    config = _config(tmp_path)
    params = deployment_parameters(config)
    template = load_deployment_template()
    fingerprint = deployment_fingerprint(template, params, tmp_path)

    rendered = render_deployment(template, params, fingerprint)

    assert "gpu='T4'" in rendered
    assert "cpu=2.0" in rendered
    assert "memory=2048" in rendered


def test_render_deployment_embeds_runtime_exec(tmp_path: Path) -> None:
    config = _config_with_runtime_exec(tmp_path)
    params = deployment_parameters(config)
    template = load_deployment_template()
    fingerprint = deployment_fingerprint(template, params, tmp_path)

    rendered = render_deployment(template, params, fingerprint)

    assert "runtime_exec='bash'" in rendered


def test_write_deployment_artifact_uses_modal_uv_state_dir(tmp_path: Path) -> None:
    path = write_deployment_artifact(tmp_path, "generated")

    assert path == tmp_path / ".modal-uv" / "deployment.py"
    assert path.read_text(encoding="utf-8") == "generated"


def test_write_deployment_artifact_is_idempotent_for_same_content(tmp_path: Path) -> None:
    path = write_deployment_artifact(tmp_path, "generated")

    write_deployment_artifact(tmp_path, "generated")

    assert path.read_text(encoding="utf-8") == "generated"


def test_ensure_deployment_current_deploys_when_app_is_missing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    deployed: list[Path] = []

    fingerprint = ensure_deployment_current(
        config,
        tmp_path,
        query_remote_fingerprint=lambda app_name: (_ for _ in ()).throw(DeploymentMissing()),
        deploy_artifact=deployed.append,
    )

    assert deployed == [tmp_path / ".modal-uv" / "deployment.py"]
    assert fingerprint in deployed[0].read_text(encoding="utf-8")


def test_ensure_deployment_current_deploys_when_fingerprint_is_stale(tmp_path: Path) -> None:
    config = _config(tmp_path)
    deployed: list[Path] = []

    ensure_deployment_current(
        config,
        tmp_path,
        query_remote_fingerprint=lambda app_name: "old-fingerprint",
        deploy_artifact=deployed.append,
    )

    assert deployed == [tmp_path / ".modal-uv" / "deployment.py"]


def test_ensure_deployment_current_skips_deploy_when_fingerprint_matches(tmp_path: Path) -> None:
    config = _config(tmp_path)
    template = load_deployment_template()
    expected = deployment_fingerprint(template, deployment_parameters(config), tmp_path)
    deployed: list[Path] = []

    fingerprint = ensure_deployment_current(
        config,
        tmp_path,
        query_remote_fingerprint=lambda app_name: expected,
        deploy_artifact=deployed.append,
    )

    assert fingerprint == expected
    assert deployed == []


def test_ensure_deployment_current_propagates_unexpected_query_errors(tmp_path: Path) -> None:
    config = _config(tmp_path)
    deployed: list[Path] = []

    with pytest.raises(RuntimeError, match="modal unavailable"):
        ensure_deployment_current(
            config,
            tmp_path,
            query_remote_fingerprint=lambda app_name: (_ for _ in ()).throw(
                RuntimeError("modal unavailable")
            ),
            deploy_artifact=deployed.append,
        )

    assert deployed == []


def test_query_deployed_fingerprint_raises_broken_on_timeout() -> None:
    import modal.exception

    with patch("modal.Function.from_name") as mock_fn:
        mock_call = MagicMock()
        mock_call.get.side_effect = modal.exception.TimeoutError("timed out")
        mock_fn.return_value.spawn.return_value = mock_call

        with pytest.raises(DeploymentBroken, match="timed out"):
            query_deployed_fingerprint("test-app")


def test_query_deployed_fingerprint_raises_missing_on_not_found() -> None:
    import modal.exception

    with patch("modal.Function.from_name") as mock_fn:
        mock_call = MagicMock()
        mock_call.get.side_effect = modal.exception.NotFoundError("no such function")
        mock_fn.return_value.spawn.return_value = mock_call

        with pytest.raises(DeploymentMissing, match="no such function"):
            query_deployed_fingerprint("test-app")


def test_query_deployed_fingerprint_uses_spawn_and_get_with_timeout() -> None:
    with patch("modal.Function.from_name") as mock_fn:
        mock_call = MagicMock()
        mock_call.get.return_value = "abc123"
        mock_fn.return_value.spawn.return_value = mock_call

        result = query_deployed_fingerprint("test-app")

        assert result == "abc123"
        mock_fn.return_value.spawn.assert_called_once()
        mock_call.get.assert_called_once_with(timeout=30)


def test_ensure_deployment_current_redeploys_on_broken_deployment(tmp_path: Path) -> None:
    config = _config(tmp_path)
    deployed: list[Path] = []

    fingerprint = ensure_deployment_current(
        config,
        tmp_path,
        query_remote_fingerprint=lambda app_name: (_ for _ in ()).throw(
            DeploymentBroken("crash-loop")
        ),
        deploy_artifact=deployed.append,
    )

    assert deployed == [tmp_path / ".modal-uv" / "deployment.py"]
    assert fingerprint in deployed[0].read_text(encoding="utf-8")
