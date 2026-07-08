# Modal-UV Exec Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the redundant `modal-uv shell` command with asynchronous `modal-uv exec -- ...` shell execution while preserving `run`, `logs`, and `abort` behavior.

**Architecture:** `run` remains the uv-managed execution mode. `exec` reuses the same deploy, sync, daemon, spawn, logs, and abort pipeline, but sends an execution mode so the Modal Worker can run a resolved shell directly without `uv run`. Optional `runtime.exec` is loaded from config and embedded into the deployment so shell resolution happens in the remote container.

**Tech Stack:** Python 3.12, Typer, Pydantic Settings, FastAPI, Modal SDK/CLI, pytest, Ruff, ty.

**Spec Reference:** `docs/superpowers/specs/2026-07-09-modal-uv-exec-design.md`

**Plan Constraint:** Per user request, this plan intentionally avoids explicit implementation code. It uses goals, definitions of done, constraints, exact files, test commands, and pseudocode.

---

## Global Constraints

- Keep changes minimal and scoped to the approved spec.
- Do not add an interactive replacement for `modal-uv shell`.
- Keep `modal-uv modal -- shell ...` as the interactive shell escape hatch.
- Do not make `exec` invoke `uv run`; `exec` must run the resolved shell directly.
- Preserve the asynchronous lifecycle: spawn quickly, print execution ID, inspect with `logs`, cancel with `abort`.
- Resolve default shell inside the Modal Worker, not in the local CLI.
- Support `runtime.exec` only when manually configured; do not add it to generated default YAML.
- Include `runtime.exec` in deployment parameters and fingerprint because it is embedded in the Worker deployment.
- Use TDD: add or update focused tests before implementation for each behavior change.
- Do not commit unless explicitly asked.

## File Structure

- Modify `src/modal_uv/config.py`: add optional `runtime.exec` config field.
- Modify `src/modal_uv/deployment.py`: include `runtime.exec` in deployment parameters and generated deployment rendering.
- Modify `src/modal_uv/app.py`: branch Worker execution between `run` and `exec` modes.
- Modify `src/modal_uv/daemon.py`: accept and forward execution mode and command args through spawn.
- Modify `src/modal_uv/cli.py`: remove `shell`, add `exec`, share async spawn output with `run`, keep default YAML omitting `runtime.exec`.
- Modify `src/modal_uv/sync.py`: add focused helpers only if useful for execution command construction; avoid broad refactors.
- Modify `tests/test_modal_uv_config.py`: cover optional `runtime.exec` parsing and default.
- Modify `tests/test_modal_uv_deployment.py`: cover deployment parameters/fingerprint rendering for `runtime.exec`.
- Modify `tests/test_modal_uv_app.py`: cover Worker `run` and `exec` execution branches.
- Modify `tests/test_modal_uv_daemon.py`: cover spawn payload mode forwarding if daemon tests currently own that boundary.
- Modify `tests/test_modal_uv_cli.py`: cover help changes, `exec` async output, daemon spawn mode, and empty exec validation.
- Modify docs only where current docs or packaged skill still mention `modal-uv shell` as a first-class command.

---

### Task 1: Config Support For Optional `runtime.exec`

**Files:**
- Modify: `src/modal_uv/config.py`
- Modify: `tests/test_modal_uv_config.py`

**Goal:** Load an optional `runtime.exec` shell command while preserving existing runtime defaults.

**Pseudocode:**

```text
RuntimeConfig:
  scaledown_window_seconds: int
  exec: optional string

RawRuntime:
  scaledown_window_seconds defaults to existing value
  exec defaults to None

load_config:
  if runtime.exec is present and non-blank:
    store stripped value
  otherwise:
    store None
```

**Steps:**

- [ ] Add a config test that minimal YAML produces `runtime.exec` as `None`.
- [ ] Add a config test that `runtime.exec: bash` loads as `bash`.
- [ ] Add a config test that blank `runtime.exec` normalizes to `None`.
- [ ] Implement the minimal config model and loader changes.
- [ ] Run `uv run pytest tests/test_modal_uv_config.py -v`.
- [ ] Run `uv run ruff check src/modal_uv/config.py tests/test_modal_uv_config.py`.

**Definition of Done:**

- `runtime.exec` is optional.
- Existing runtime defaults are unchanged.
- Manual `runtime.exec` values load predictably.
- No generated template includes `runtime.exec` yet.

---

### Task 2: Deployment Parameters And Fingerprint Include `runtime.exec`

**Files:**
- Modify: `src/modal_uv/deployment.py`
- Modify: `tests/test_modal_uv_deployment.py`

**Goal:** Ensure changing `runtime.exec` changes the deployed Worker configuration and deployment fingerprint.

**Pseudocode:**

```text
deployment_parameters(config):
  runtime.scaledown_window_seconds = config runtime scaledown
  runtime.exec = config runtime exec

render_deployment(parameters):
  pass runtime.exec into generated app template

deployment_fingerprint:
  already hashes deployment parameters
  no separate fingerprint logic needed if parameters include runtime.exec
```

**Steps:**

- [ ] Add or update deployment-parameter tests to assert `runtime.exec` appears as `None` when omitted.
- [ ] Add or update deployment-parameter tests to assert configured `runtime.exec` appears in parameters.
- [ ] Add or update fingerprint tests to prove changing `runtime.exec` changes the fingerprint.
- [ ] Add or update rendering tests to prove generated deployment embeds the configured exec value.
- [ ] Implement the minimal deployment parameter and rendering changes.
- [ ] Run `uv run pytest tests/test_modal_uv_deployment.py -v`.
- [ ] Run `uv run ruff check src/modal_uv/deployment.py tests/test_modal_uv_deployment.py`.

**Definition of Done:**

- `runtime.exec` is included in deployment parameters.
- Deployment fingerprint changes when `runtime.exec` changes.
- Generated deployment has the data needed for remote shell resolution.

---

### Task 3: Worker Execution Mode Branching

**Files:**
- Modify: `src/modal_uv/app.py`
- Modify: `tests/test_modal_uv_app.py`
- Modify: `src/modal_uv/sync.py` only if a helper boundary is needed

**Goal:** Keep one Worker sync path, but execute either uv-managed `run` mode or direct-shell `exec` mode after sync completes.

**Pseudocode:**

```text
Worker.sync_and_run(manifest, files, args, mode):
  sync files exactly as today
  write remote state exactly as today
  start volume commit threads exactly as today

  if mode is run:
    execute uv_run_command(args)

  else if mode is exec:
    command = first exec command string from args
    shell = configured runtime.exec or remote SHELL env or /bin/sh
    execute shell with -c command directly

  else:
    fail with clear unknown mode error

  stop commit threads and final commit exactly as today
  return subprocess return code
```

**Steps:**

- [ ] Add a Worker test proving `run` mode still executes through `uv_run_command`.
- [ ] Add a Worker test proving `exec` mode executes the resolved shell directly and does not call `uv_run_command`.
- [ ] Add Worker tests for shell resolution order: configured shell, remote `$SHELL`, fallback `/bin/sh`.
- [ ] Add a Worker test for unknown mode producing a clear error.
- [ ] Implement the minimal Worker method signature and branch.
- [ ] Keep volume commit setup, cleanup, and return-code behavior unchanged.
- [ ] Run `uv run pytest tests/test_modal_uv_app.py -v`.
- [ ] Run `uv run ruff check src/modal_uv/app.py tests/test_modal_uv_app.py`.

**Definition of Done:**

- `run` behavior remains unchanged except for explicit mode plumbing.
- `exec` runs direct shell commands without `uv run`.
- Shell resolution happens in the Worker process.
- Unknown modes fail clearly.
- Volume commits still happen for both modes.

---

### Task 4: Daemon Spawn Protocol Carries Execution Mode

**Files:**
- Modify: `src/modal_uv/daemon.py`
- Modify: `tests/test_modal_uv_daemon.py`

**Goal:** The daemon accepts execution mode from the CLI and forwards it to the Worker spawn call.

**Pseudocode:**

```text
Spawn request body:
  args: list of strings
  mode: run or exec, default run if preserving compatibility is useful internally

/spawn handler:
  validate daemon repo root and Worker exist
  call Worker.sync_and_run.spawn(manifest, payloads, args, mode)
  return execution ID exactly as today
```

**Steps:**

- [ ] Add daemon test that omitted or explicit `run` mode forwards `run` to Worker.
- [ ] Add daemon test that `exec` mode forwards `exec` to Worker.
- [ ] Add daemon test that invalid mode is rejected before Worker spawn.
- [ ] Implement the request model and spawn forwarding changes.
- [ ] Run `uv run pytest tests/test_modal_uv_daemon.py -v`.
- [ ] Run `uv run ruff check src/modal_uv/daemon.py tests/test_modal_uv_daemon.py`.

**Definition of Done:**

- Spawn requests carry execution mode.
- Existing `run` callers continue to work.
- `exec` callers receive the same execution ID response shape as `run`.
- Invalid modes do not reach the Worker spawn call.

---

### Task 5: CLI `exec` Command And `shell` Removal

**Files:**
- Modify: `src/modal_uv/cli.py`
- Modify: `tests/test_modal_uv_cli.py`

**Goal:** Remove `modal-uv shell`, add `modal-uv exec -- ...`, and preserve async output behavior.

**Pseudocode:**

```text
shared_spawn(project, config, args, mode):
  ensure deployment with notice
  build manifest
  compute expected fingerprint
  plan sync
  spawn with args and mode
  print execution ID, logs hint, abort hint

run command:
  mode = run
  args = passed uv args

exec command:
  require at least one arg
  command = shlex.join(args)
  mode = exec
  args = list containing command string

shell command:
  remove command registration and implementation
```

**Steps:**

- [ ] Update help test to assert `shell` is absent and `exec` is present.
- [ ] Add CLI test that `exec -- nvidia-smi` prints execution ID, logs hint, and abort hint.
- [ ] Add CLI test that `exec` sends `mode: exec` in the spawn request.
- [ ] Add CLI test that `exec` uses shell-safe joining for multiple command tokens.
- [ ] Add CLI test that empty `exec` fails locally with a clear error.
- [ ] Update existing `run` tests to expect `mode: run` if the payload assertion needs changing.
- [ ] Remove the `shell` command implementation.
- [ ] Add `exec` command implementation and any small shared helper needed to avoid duplicating `run` logic.
- [ ] Run `uv run pytest tests/test_modal_uv_cli.py -v`.
- [ ] Run `uv run ruff check src/modal_uv/cli.py tests/test_modal_uv_cli.py`.

**Definition of Done:**

- `modal-uv shell` is no longer a command.
- `modal-uv exec` is listed in help.
- `exec` returns immediately with the same execution guidance as `run`.
- Empty exec commands fail before remote spawn.
- `run` behavior and output remain unchanged.

---

### Task 6: Default Config, Example Config, Skill, And Docs Cleanup

**Files:**
- Modify: `src/modal_uv/cli.py` if default YAML lives there
- Modify: `example-repo/modal-uv.yaml`
- Modify: `skills/use-modal-uv/SKILL.md`
- Modify: `README.md` if it exists and mentions `modal-uv shell`
- Modify tests that snapshot or assert generated config text

**Goal:** Public guidance matches the new command surface and generated config omits `runtime.exec`.

**Pseudocode:**

```text
default modal-uv.yaml:
  keep runtime.scaledown_window_seconds if already present
  do not include runtime.exec

docs and skill:
  replace first-class shell guidance with modal CLI passthrough guidance
  add exec examples for shell commands
  keep run examples for uv-managed Python/project commands
```

**Steps:**

- [ ] Search docs, README, skill, tests, and example config for `modal-uv shell`.
- [ ] Update public examples to use `modal-uv exec -- ...` for shell commands.
- [ ] Update interactive shell guidance to `modal-uv modal -- shell ...`.
- [ ] Ensure generated default YAML does not include `runtime.exec`.
- [ ] Ensure example config does not include `runtime.exec` unless it is intentionally demonstrating manual override; default to omission.
- [ ] Run focused tests for config generation if present.
- [ ] Run `uv run ruff format --check` after doc/test edits if Python formatting may be affected.

**Definition of Done:**

- No primary docs or skill quick-start advertise `modal-uv shell`.
- Docs clearly distinguish `run` as uv-managed and `exec` as shell-managed.
- Default generated config omits `runtime.exec`.

---

### Task 7: Full Verification And Smoke Check

**Files:**
- No planned source changes unless verification exposes defects.

**Goal:** Prove the implementation passes the repo gate and, if credentials/environment allow, performs a real remote `exec` smoke.

**Steps:**

- [ ] Run `uv run pytest`.
- [ ] Run `uv run ruff format --check`.
- [ ] Run `uv run ty check`.
- [ ] Run `uv run ruff check`.
- [ ] Run `uv build`.
- [ ] If Modal auth and installed tool environment are available, reinstall locally with `uv tool install --force --reinstall --refresh /home/ofek/repos/modal-uv`.
- [ ] If Modal smoke is feasible, run `cd example-repo` then `modal-uv exec -- pwd` and capture the execution ID.
- [ ] If Modal smoke is feasible, run `modal-uv logs <execution-id>` and verify the remote command output appears.

**Definition of Done:**

- All unit, lint, type, and build checks pass.
- Smoke test is either passing or explicitly documented as skipped with the reason.
- Worktree status contains only intended files.

---

## Overall Definition Of Done

- `modal-uv shell` is removed.
- `modal-uv modal -- shell ...` remains available.
- `modal-uv exec -- ...` exists and uses the same async execution lifecycle as `run`.
- `exec` mode syncs files before running.
- `exec` mode runs a resolved remote shell directly without `uv run`.
- `run` mode still uses `uv run --link-mode copy`.
- `runtime.exec` is optional, manually configurable, omitted from default generated YAML, and included in deployment fingerprint inputs.
- Tests cover config, deployment, Worker behavior, daemon protocol, CLI behavior, and docs/config defaults.
- Verification commands pass or any skipped external smoke is explained.
