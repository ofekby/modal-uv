"""Tests for modal-uv skill installer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from modal_uv.skill import (
    KNOWN_AGENTS,
    install_to_agent,
    install_to_all_present,
    install_to_dir,
    load_packaged_skill,
    present_agents,
)


def test_load_packaged_skill_returns_non_empty_text() -> None:
    text = load_packaged_skill()
    assert "modal-uv" in text
    assert "name: use-modal-uv" in text


def test_known_agents_cover_opencode_claude_agents() -> None:
    assert set(KNOWN_AGENTS) == {"opencode", "claude", "agents"}


def test_present_agents_returns_only_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".config" / "opencode").mkdir(parents=True)

    agents = present_agents()

    assert agents == ["opencode"]


def test_present_agents_returns_empty_when_none_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    assert present_agents() == []


def test_install_to_agent_creates_skill_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    path = install_to_agent("opencode")

    assert path == tmp_path / ".config" / "opencode" / "skills" / "use-modal-uv" / "SKILL.md"
    assert path.read_text(encoding="utf-8") == load_packaged_skill()


def test_install_to_agent_overwrites_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    target = tmp_path / ".config" / "opencode" / "skills" / "use-modal-uv" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("old content", encoding="utf-8")

    path = install_to_agent("opencode")

    assert path.read_text(encoding="utf-8") == load_packaged_skill()


def test_install_to_agent_rejects_unknown_agent() -> None:
    with pytest.raises(ValueError, match="unknown agent"):
        install_to_agent("unknown-agent")


def test_install_to_dir_creates_skill_under_explicit_path(tmp_path: Path) -> None:
    custom = tmp_path / "my-agent" / "skills"

    path = install_to_dir(custom)

    assert path == custom / "use-modal-uv" / "SKILL.md"
    assert path.read_text(encoding="utf-8") == load_packaged_skill()


def test_install_to_all_present_installs_to_each_present_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".config" / "opencode").mkdir(parents=True)
    (tmp_path / ".claude").mkdir()

    paths = install_to_all_present()

    assert len(paths) == 2
    for p in paths:
        assert p.read_text(encoding="utf-8") == load_packaged_skill()


def test_install_to_all_present_returns_empty_when_none_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    assert install_to_all_present() == []


@patch("modal_uv.skill.load_packaged_skill")
def test_install_uses_packaged_skill_content(mock_load: MagicMock, tmp_path: Path) -> None:
    mock_load.return_value = "fake skill content"
    path = install_to_dir(tmp_path)
    assert path.read_text(encoding="utf-8") == "fake skill content"
