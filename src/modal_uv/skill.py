"""Skill installer for modal-uv agent integration."""

from __future__ import annotations

from pathlib import Path


def _agent_config_dir(agent: str) -> Path:
    home = Path.home()
    if agent == "opencode":
        return home / ".config" / "opencode"
    if agent == "claude":
        return home / ".claude"
    if agent == "agents":
        return home / ".agents"
    raise ValueError(f"unknown agent: {agent}")


KNOWN_AGENTS: dict[str, str] = {
    "opencode": "opencode",
    "claude": "claude",
    "agents": "agents",
}

SKILL_DIR = "skills"
SKILL_NAME = "use-modal-uv"
SKILL_FILE = "SKILL.md"


def _skill_target(agent_config_dir: Path) -> Path:
    return agent_config_dir / SKILL_DIR / SKILL_NAME / SKILL_FILE


def load_packaged_skill() -> str:
    """Load the packaged SKILL.md text."""
    try:
        from importlib.resources import files

        resource = files("modal_uv") / "skill" / SKILL_FILE
        if resource.is_file():
            return resource.read_text(encoding="utf-8")
    except (ImportError, FileNotFoundError, OSError):
        pass

    current = Path(__file__).resolve()
    for parent in (current, *current.parents):
        candidate = parent / "skills" / SKILL_NAME / SKILL_FILE
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")

    raise FileNotFoundError("packaged skill SKILL.md not found")


def present_agents() -> list[str]:
    """Return agent names whose config directories exist."""
    return [name for name in KNOWN_AGENTS if _agent_config_dir(name).is_dir()]


def install_to_agent(name: str) -> Path:
    """Install the skill to a known agent's skill directory."""
    target = _skill_target(_agent_config_dir(name))
    _write_skill(target)
    return target


def install_to_dir(directory: Path) -> Path:
    """Install the skill under an explicit directory."""
    target = directory / SKILL_NAME / SKILL_FILE
    _write_skill(target)
    return target


def install_to_all_present() -> list[Path]:
    """Install the skill to every present agent. Returns installed paths."""
    paths: list[Path] = []
    for name in present_agents():
        paths.append(install_to_agent(name))
    return paths


def _write_skill(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(load_packaged_skill(), encoding="utf-8")
