# modal-uv

Run `uv` commands on Modal.com with GPU support, direct file sync, async execution IDs, logs, abort, and persistent Modal volumes.

## Installation

### Option 1: Coding Agent (Recommended)

Paste this prompt to your coding agent (opencode, Claude Code, Gemini CLI, etc.):

```
Install modal-uv globally and set it up:
1. Run: pip install modal-uv
2. Run: modal-uv onboard
   - This opens a browser for Modal OAuth authentication
   - Complete the auth flow in the browser
   - It also installs the use-modal-uv skill to detected coding agents
3. In the project repo, run: modal-uv init
   - This creates modal-uv.yaml with defaults if missing
   - It creates .modal-uv/ for generated state and adds it to .gitignore
4. Edit modal-uv.yaml to set app_name, runtime.gpu, and volumes[].name for this project
5. Run: modal-uv doctor
   - This checks modal-uv health: auth state, volume existence, app deployment, daemon status
   - Does not wake the container
```

### Option 2: Manual Getting Started

```bash
pip install modal-uv
```

Authenticate with Modal (opens browser for OAuth):

```bash
modal-uv onboard
```

This also installs the `use-modal-uv` skill to detected coding agents (`~/.config/opencode/`, `~/.claude/`, `~/.agents/`).

In your project repo, initialize modal-uv files:

```bash
modal-uv init
```

This creates `modal-uv.yaml` with defaults (using the directory name as `app_name`) if missing, and creates `.modal-uv/` for generated state with a `.gitignore` entry.

Edit `modal-uv.yaml` to configure your app:

```yaml
app_name: "my-project"
work_dir: "/tmp/work"

volumes:
  - name: "modal-uv-cache"
    mount_path: "/mnt/volume"
    commit_interval_seconds: 30

env: {}

runtime:
  timeout_seconds: 3600
  scaledown_window_seconds: 300

image:
  base_image: "python:3.12-slim"

sync:
  ignore:
    - "data/**"
    - "*.ckpt"
```

Then run commands on Modal:

```bash
modal-uv run -- pytest
```

## Repository Configuration

`modal-uv.yaml` at the repository root is discovered by walking up from the current directory, similar to `git` or `uv`.

Fields:

- `app_name`: Modal app name (required)
- `work_dir`: Working directory inside the Modal container (default: `/root/work`)
- `volumes`: Modal volumes to mount in the container; may be empty or omitted
- `volumes[].name`: Modal volume name
- `volumes[].mount_path`: Mount path in the container (default: `/root/.cache`)
- `volumes[].commit_interval_seconds`: Periodic Modal Volume commit interval while a command runs (default: `30`)
- `env`: Extra container environment variables merged over modal-uv defaults
- `runtime`: Optional Modal runtime settings; omit the section or individual fields to use defaults
- `runtime.gpu`: Optional GPU type, such as `T4`, `A10G`, `A100`, `H100`, or `L4`; omit for CPU-only containers
- `runtime.cpu`: Optional Modal CPU request
- `runtime.memory`: Optional Modal memory request in MiB
- `runtime.timeout_seconds`: Modal Function execution timeout in seconds (default: `3600`)
- `runtime.scaledown_window_seconds`: Modal worker scaledown window (default: `300`)
- `runtime.exec`: Optional shell executable for `modal-uv exec`; if omitted, the remote Worker uses `$SHELL`, then `/bin/sh`
- `image.base_image`: Base Docker image (default: `python:3.12-slim`)
- `image.add_python_version`: Required for non-Python base images; use `"inherit"` if the image already has Python, or a version like `"3.12"` to add Python via Modal's `add_python`
- `sync.ignore`: gitignore-style patterns excluded from direct sync

## Repo-Local State

`modal-uv` creates `.modal-uv/` at the repo root for generated/runtime files and ensures the root `.gitignore` ignores it.

Examples of generated files:

- `.modal-uv/deployment.py`
- `.modal-uv/daemon.pid`
- `.modal-uv/daemon.sock`
- `.modal-uv/daemon.log`

`.modal-uv/` is not normally synced to the Modal work directory.

## Sync And Deployment

`modal-uv run` and `modal-uv exec` scan local files, apply built-in ignores plus `sync.ignore`, ask the warm Modal container which files are missing or stale, upload only those files, spawn the execution, print the Modal function call ID, and return immediately.

The detached daemon lazily ensures the Modal app is deployed before running work. It generates `.modal-uv/deployment.py` and redeploys when the deployment fingerprint changes. The fingerprint includes the deployment template, Modal-relevant config values, and the repo `pyproject.toml` SHA256 when present.

During a running command, `modal-uv` periodically commits each Modal Volume every `volumes[].commit_interval_seconds` seconds, plus one final commit after the command exits. This persists outputs and checkpoints written under mounted volumes during long runs.

Ordinary source changes do not redeploy the app; they are handled by direct sync.

Modal authentication remains Modal's normal user-global authentication. `modal-uv` does not create repo-local auth files.

## Commands

Run `uv` commands on Modal:

```bash
modal-uv run -- pytest
modal-uv run -- python -m lab
modal-uv run -- python train.py --epochs 10
```

Tail or abort a spawned execution:

```bash
modal-uv logs fc-...
modal-uv abort fc-...
```

Run shell-style commands in the synced Modal work directory:

```bash
modal-uv exec -- nvidia-smi
modal-uv exec -- 'ls -la && pwd'
modal-uv exec -- 'python --version && nproc'
```

Quote command strings containing shell metacharacters such as `&&`, `|`, `>`, `<`, `*`, or variable expansions. Without quotes, your local shell may interpret those operators before `modal-uv` receives the command.

Open Modal's native interactive shell through the passthrough command:

```bash
modal-uv modal -- shell
```

Show Modal app status:

```bash
modal-uv status
```

Check the configured Modal volume directly:

```bash
modal-uv modal -- volume ls modal-uv-cache
```

Initialize or align modal-uv files in the current directory:

```bash
modal-uv init
```

Run any Modal CLI command through the modal-uv environment:

```bash
modal-uv modal -- app list
modal-uv modal -- volume ls
```

Daemon helpers:

```bash
modal-uv daemon-status
modal-uv daemon-stop
```

## Updates

Upgrade modal-uv and refresh the skill on all detected agents:

```bash
modal-uv update
```

Install the skill to a specific agent (`opencode`, `claude`, `agents`) or an explicit directory path:

```bash
modal-uv install-skill opencode
modal-uv install-skill /path/to/skills/dir
```

Detected agents are based on which config directories exist (`~/.config/opencode/`, `~/.claude/`, `~/.agents/`).

Use `--config` or `-c` to specify a custom config file:

```bash
modal-uv run --config path/to/modal-uv.yaml -- pytest
```

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```
