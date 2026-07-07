# Modal-UV Global CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt `modal-uv` into a globally installed CLI that discovers repo config, stores repo-local generated state under `.modal-uv/`, uses `sync.ignore`, removes `py`/preload behavior, and lazily self-deploys the Modal app from a detached daemon.

**Architecture:** The foreground CLI owns only local repo discovery, config loading, manifest building, and daemon communication. The detached daemon owns all Modal SDK interactions, including generated deployment artifact refresh, fingerprint checks, lazy deploy/redeploy, and Worker initialization. Repo-local generated state is isolated in `.modal-uv/`, which is ignored by git and normal sync.

**Tech Stack:** Python 3.12, Typer, Pydantic Settings, FastAPI, Uvicorn over Unix sockets, httpx, Modal SDK/CLI, pathspec, pytest, Ruff.

**Spec Reference:** `docs/superpowers/specs/2026-07-06-modal-uv-global-cli-design.md`

---

## Global Constraints

- Do not add backward compatibility for `.s3-sync-ignore`.
- Do not keep `modal-uv py`, `/spawn_python`, `sync_and_run_python`, preload config, or in-process Python execution helpers.
- Do not move Modal authentication into repo-local files.
- Do not import or call Modal SDK deployment operations from foreground CLI command handlers.
- Keep all repo runtime/generated files under `.modal-uv/`.
- Ensure root `.gitignore` ignores `.modal-uv/` when `.modal-uv/` is created.
- Treat `.modal-uv/` as both gitignored and normally sync-ignored.
- Keep changes minimal and focused on the approved spec.
- Use tests to lock each behavior before or alongside implementation.

## File Structure

- Modify `src/modal_uv/config.py`: add repo discovery helpers, add `sync.ignore`, remove `preload` config.
- Modify `src/modal_uv/paths.py`: move daemon paths under `.modal-uv/`, add repo-state path helpers.
- Modify `src/modal_uv/sync.py`: consume configured ignore patterns, remove `.s3-sync-ignore`, remove Python/preload helpers.
- Modify `src/modal_uv/cli.py`: use repo discovery/context, remove `py`, pass deployment/config inputs to daemon.
- Modify `src/modal_uv/client.py`: use `.modal-uv/` daemon paths, pass daemon startup inputs, improve daemon log errors.
- Modify `src/modal_uv/daemon.py`: remove Python endpoint, add lazy deployment initialization before Worker use.
- Modify `src/modal_uv/app.py`: remove preload and Python worker method; keep `run` worker behavior.
- Create `src/modal_uv/deployment.py` or similarly focused module: deployment artifact rendering, fingerprint calculation, deployment status decisions. Keep Modal SDK usage reachable only from daemon execution paths.
- Create package template resource for generated `.modal-uv/deployment.py`: owns Modal app definition text used by deploy.
- Modify `tests/test_modal_uv_config.py`: repo discovery, `sync.ignore`, preload removal.
- Modify `tests/test_modal_uv_sync.py`: built-in ignores, `sync.ignore`, `.s3-sync-ignore` replacement, Python/preload removal.
- Modify `tests/test_modal_uv_cli.py`: no `py` command, repo-root discovery from nested cwd, foreground daemon calls.
- Modify `tests/test_modal_uv_daemon.py`: `.modal-uv/` daemon paths, no Python endpoint, lazy deploy behavior with mocks.
- Modify `tests/test_modal_uv_app.py`: remove preload/Python-worker expectations.
- Add tests for deployment fingerprint and deployment decision logic.
- Update `README.md`, `modal-uv.yaml`, and `skills/use-modal-uv/SKILL.md` to match the new command/config model.

---

### Task 1: Repo Discovery And Repo State Paths

**Files:**
- Modify: `src/modal_uv/config.py`
- Modify: `src/modal_uv/paths.py`
- Modify: `tests/test_modal_uv_config.py`
- Add or modify tests for path helpers in the existing relevant test file

**Goal:** Commands can run from any nested directory inside a repo containing `modal-uv.yaml`, and all repo-local runtime paths resolve under `.modal-uv/`.

**Pseudocode:**

```text
resolve_project(config_path):
  if config_path is provided:
    return ProjectContext(repo_root=config_path.parent, config_path=config_path)

  current = cwd
  for current and each parent:
    candidate = current / "modal-uv.yaml"
    if candidate exists:
      return ProjectContext(repo_root=current, config_path=candidate)

  raise ConfigError explaining upward discovery failed

repo_state_dir(repo_root):
  return repo_root / ".modal-uv"

daemon_paths(repo_root):
  state = repo_state_dir(repo_root)
  return state / "daemon.pid", state / "daemon.sock"

daemon_log_path(repo_root):
  return repo_state_dir(repo_root) / "daemon.log"
```

**Steps:**

- [ ] Add tests that nested cwd resolves to the nearest ancestor containing `modal-uv.yaml`.
- [ ] Add tests that `--config` uses the config file parent as repo root.
- [ ] Add tests that missing config raises a clear `ConfigError`.
- [ ] Add tests that daemon pid/socket/log paths are under `.modal-uv/`.
- [ ] Implement repo discovery and repo-state path helpers.
- [ ] Run `uv run pytest tests/test_modal_uv_config.py -v`.
- [ ] Run the focused daemon/path helper tests.
- [ ] Run `uv run ruff check src/modal_uv/config.py src/modal_uv/paths.py tests/test_modal_uv_config.py`.

**Definition of Done:**

- Repo root discovery works from nested directories.
- `--config` remains an explicit override.
- Missing config errors mention `modal-uv.yaml` and parent discovery.
- Daemon files no longer resolve to repo root files.

---

### Task 2: `.modal-uv/` Creation And Root `.gitignore`

**Files:**
- Modify: `src/modal_uv/paths.py` or create a small repo-state helper module if needed
- Modify: `src/modal_uv/cli.py`
- Add tests in `tests/test_modal_uv_cli.py` or a focused paths/config test

**Goal:** First use creates `.modal-uv/` and ensures root `.gitignore` ignores `.modal-uv/`.

**Pseudocode:**

```text
ensure_repo_state(repo_root):
  create repo_root / ".modal-uv"
  gitignore = repo_root / ".gitignore"
  if gitignore does not exist:
    write ".modal-uv/" entry
  else if no existing rule ignores exactly ".modal-uv/" or ".modal-uv":
    append a newline if needed, then append ".modal-uv/"
```

**Steps:**

- [ ] Add test for creating `.modal-uv/` and `.gitignore` when neither exists.
- [ ] Add test for appending `.modal-uv/` to an existing `.gitignore` without corrupting existing entries.
- [ ] Add test that repeated calls do not duplicate `.modal-uv/`.
- [ ] Wire repo-state creation into repo-requiring CLI commands before daemon startup.
- [ ] Run focused CLI/path tests.
- [ ] Run `uv run ruff check src tests` for touched files.

**Definition of Done:**

- `.modal-uv/` is created automatically.
- Root `.gitignore` contains exactly one effective `.modal-uv/` entry after first use.
- There is no `.modal-uv/.gitignore` behavior.

---

### Task 3: Config Shape For `sync.ignore` And Preload Removal

**Files:**
- Modify: `src/modal_uv/config.py`
- Modify: `tests/test_modal_uv_config.py`
- Modify: `modal-uv.yaml`

**Goal:** `modal-uv.yaml` supports `sync.ignore` and no longer exposes `preload`.

**Pseudocode:**

```text
ModalUVConfig includes:
  app_name
  gpu
  work_dir
  volume
  image
  sync.ignore as tuple of non-empty strings

load_config(project_context):
  read project_context.config_path
  env overrides still apply where supported
  normalize sync.ignore by trimming blank entries
  return config without preload
```

**Steps:**

- [ ] Add test that `sync.ignore` parses into an immutable tuple/list on config.
- [ ] Add test that omitted `sync.ignore` defaults to empty.
- [ ] Remove or rewrite tests that assert `preload.imports` exists.
- [ ] Remove preload config models and fields.
- [ ] Update copied sample `modal-uv.yaml` to use `sync.ignore` and no `preload`.
- [ ] Run `uv run pytest tests/test_modal_uv_config.py -v`.
- [ ] Run `uv run ruff check src/modal_uv/config.py tests/test_modal_uv_config.py`.

**Definition of Done:**

- Config object exposes `sync.ignore`.
- Config object no longer exposes `preload`.
- Sample config matches the new shape.

---

### Task 4: Sync Ignore Behavior

**Files:**
- Modify: `src/modal_uv/sync.py`
- Modify: `src/modal_uv/cli.py`
- Modify: `tests/test_modal_uv_sync.py`

**Goal:** Manifest building uses built-in ignores plus `sync.ignore`, ignores `.modal-uv/`, and never reads `.s3-sync-ignore`.

**Pseudocode:**

```text
TrackingConfig:
  include defaults to all files
  ignore comes from config.sync.ignore

IgnoreMatcher.load(repo_root, ignore_patterns):
  patterns = built-in ignores including ".modal-uv/"
  patterns += ignore_patterns
  return gitignore-style matcher

iter_sync_files(repo_root, tracking_config):
  walk repo tree
  prune ignored directories
  include files matching include patterns and not ignored
```

**Steps:**

- [ ] Add test that `sync.ignore` excludes matching files.
- [ ] Add test that `.modal-uv/` is ignored by built-ins.
- [ ] Add test that a present `.s3-sync-ignore` does not affect the manifest.
- [ ] Update `TrackingConfig` and matcher loading to accept configured ignore patterns.
- [ ] Update CLI manifest creation to pass `config.sync.ignore`.
- [ ] Run `uv run pytest tests/test_modal_uv_sync.py -v`.
- [ ] Run focused CLI tests that mock manifest creation.

**Definition of Done:**

- `sync.ignore` is the only user-configurable sync ignore source.
- `.s3-sync-ignore` is inert.
- `.modal-uv/` is never included in normal sync payloads.

---

### Task 5: Remove `modal-uv py`, In-Process Python, And Preload

**Files:**
- Modify: `src/modal_uv/cli.py`
- Modify: `src/modal_uv/daemon.py`
- Modify: `src/modal_uv/app.py`
- Modify: `src/modal_uv/sync.py`
- Modify: `tests/test_modal_uv_cli.py`
- Modify: `tests/test_modal_uv_daemon.py`
- Modify: `tests/test_modal_uv_app.py`
- Modify: `tests/test_modal_uv_sync.py`

**Goal:** Remove the Python warm-worker feature and all support code that only existed for it.

**Pseudocode:**

```text
CLI commands:
  keep run/logs/abort/shell/status/daemon-stop/daemon-status
  remove py

Daemon endpoints:
  keep ping/plan_sync/spawn
  remove spawn_python

Worker methods:
  keep plan_sync/sync_and_run
  remove sync_and_run_python

Sync helpers:
  keep file payload, manifest, uv run command/env, state csv, plan sync
  remove PythonExecutionRequest, parse_python_args, execute_python, preload helpers
```

**Steps:**

- [ ] Update CLI help test to assert `py` is absent and remaining commands are present.
- [ ] Remove tests for `py`, Python execution, and preload.
- [ ] Remove CLI command and imports for Python execution.
- [ ] Remove daemon Python request model and endpoint.
- [ ] Remove Worker Python method and preload enter hook.
- [ ] Remove sync helpers that only support Python/preload.
- [ ] Run `uv run pytest tests/test_modal_uv_cli.py tests/test_modal_uv_daemon.py tests/test_modal_uv_app.py tests/test_modal_uv_sync.py -v`.
- [ ] Run `uv run ruff check src tests`.

**Definition of Done:**

- `modal-uv py` no longer appears in help.
- No production code references `PythonExecutionRequest`, `execute_python`, `parse_python_args`, or preload helpers.
- Remaining `run` path continues to use `uv run --link-mode copy`.

---

### Task 6: Deployment Fingerprint Model

**Files:**
- Create or modify: `src/modal_uv/deployment.py`
- Add tests: `tests/test_modal_uv_deployment.py`

**Goal:** Deterministically identify whether the deployed Modal app matches local deployment inputs.

**Pseudocode:**

```text
deployment_parameters(config):
  select only fields that affect Modal app deployment
  include app_name, gpu, work_dir, volume, image
  exclude sync.ignore because it affects local payload selection, not deployed app shape

hash_file(path):
  if path exists:
    return sha256(file bytes)
  return null marker

deployment_fingerprint(template_text, parameters, repo_root):
  canonical_json = stable JSON for parameters and pyproject hash
  return sha256(template_text + canonical_json)
```

**Steps:**

- [ ] Add test that fingerprint is stable for identical inputs.
- [ ] Add test that fingerprint changes when template text changes.
- [ ] Add test that fingerprint changes when deployment parameters change.
- [ ] Add test that fingerprint changes when `pyproject.toml` changes.
- [ ] Add test that missing `pyproject.toml` is handled deterministically.
- [ ] Implement fingerprint helpers without Modal SDK dependencies.
- [ ] Run `uv run pytest tests/test_modal_uv_deployment.py -v`.
- [ ] Run `uv run ruff check src/modal_uv/deployment.py tests/test_modal_uv_deployment.py`.

**Definition of Done:**

- Fingerprint inputs match the spec.
- Fingerprint logic is testable without Modal.
- Sync-only config does not trigger redeploys.

---

### Task 7: Generated Deployment Artifact

**Files:**
- Add package deployment template resource
- Modify: `src/modal_uv/deployment.py`
- Add tests: `tests/test_modal_uv_deployment.py`

**Goal:** The daemon can generate `.modal-uv/deployment.py` from a package-owned template and current deployment parameters.

**Pseudocode:**

```text
render_deployment(template_text, parameters, fingerprint):
  substitute app name, gpu, work dir, volume, image, fingerprint
  produce deterministic deployment file text

write_deployment(repo_root, rendered_text):
  ensure .modal-uv exists
  write .modal-uv/deployment.py only if content differs
```

**Steps:**

- [ ] Add test that rendering is deterministic for identical inputs.
- [ ] Add test that generated deployment contains the embedded fingerprint.
- [ ] Add test that artifact path is `.modal-uv/deployment.py`.
- [ ] Add test that writing is idempotent when content is unchanged.
- [ ] Add template resource and rendering/writing helpers.
- [ ] Run `uv run pytest tests/test_modal_uv_deployment.py -v`.
- [ ] Run `uv run ruff check src tests/test_modal_uv_deployment.py`.

**Definition of Done:**

- `.modal-uv/deployment.py` can be generated without foreground Modal SDK calls.
- Generated file is deterministic for a given template/config/fingerprint.
- Generated file embeds the fingerprint query surface needed by the daemon.

---

### Task 8: Daemon Lazy Deploy Decision

**Files:**
- Modify: `src/modal_uv/daemon.py`
- Modify: `src/modal_uv/deployment.py`
- Modify: `src/modal_uv/client.py`
- Add or modify: `tests/test_modal_uv_daemon.py`
- Add or modify: `tests/test_modal_uv_deployment.py`

**Goal:** The daemon deploys only when the app is missing or fingerprint-stale, then initializes Worker.

**Pseudocode:**

```text
ensure_deployed(config, repo_root):
  template = load package template
  parameters = deployment_parameters(config)
  fingerprint = deployment_fingerprint(template, parameters, repo_root)
  deployment_path = write generated deployment artifact

  if app missing:
    deploy deployment_path
    return fingerprint

  remote_fingerprint = query deployed fingerprint
  if remote_fingerprint != fingerprint:
    deploy deployment_path

  return fingerprint

daemon startup:
  receive serialized config inputs
  ensure_deployed before Worker from_name
  only then assign Worker handle
```

**Steps:**

- [ ] Add test for missing app causing deploy.
- [ ] Add test for stale fingerprint causing deploy.
- [ ] Add test for matching fingerprint skipping deploy.
- [ ] Add test that unexpected fingerprint query errors fail loudly.
- [ ] Add test that Worker initialization happens after deploy check.
- [ ] Update daemon startup inputs so it receives enough config to deploy.
- [ ] Keep Modal SDK interactions in daemon/deployment execution path, not CLI handlers.
- [ ] Run daemon and deployment tests.
- [ ] Run `uv run ruff check src/modal_uv/daemon.py src/modal_uv/deployment.py src/modal_uv/client.py tests`.

**Definition of Done:**

- Daemon can lazily make deployment current before sync/run.
- Matching deployments are reused.
- Missing/stale deployments are redeployed.
- Foreground CLI remains free of Modal deployment calls.

---

### Task 9: Foreground CLI Integration

**Files:**
- Modify: `src/modal_uv/cli.py`
- Modify: `src/modal_uv/client.py`
- Modify: `tests/test_modal_uv_cli.py`

**Goal:** CLI commands use project context, ensure repo state, build manifests with `sync.ignore`, and communicate with the daemon using `.modal-uv/` paths.

**Pseudocode:**

```text
repo_command_setup(config_path):
  project = resolve_project(config_path)
  config = load_config(project.config_path)
  ensure_repo_state(project.repo_root)
  return project, config

run command:
  project, config = setup
  manifest = build_manifest(project.repo_root, TrackingConfig(ignore=config.sync.ignore))
  client = ensure_daemon(config, project.repo_root)
  plan sync
  spawn uv run args
  print execution id and hints

logs/status/shell/abort:
  use discovered config when app/volume metadata is required
  do not require manifest build unless syncing/running
```

**Steps:**

- [ ] Add CLI test for running from nested cwd without `--config`.
- [ ] Add CLI test that `run` passes configured ignores to manifest building.
- [ ] Add CLI test that daemon startup receives deployment-capable config inputs.
- [ ] Add CLI test that daemon status/stop use `.modal-uv/` paths via repo discovery.
- [ ] Update command handlers to share repo setup behavior.
- [ ] Run `uv run pytest tests/test_modal_uv_cli.py -v`.
- [ ] Run `uv run ruff check src/modal_uv/cli.py src/modal_uv/client.py tests/test_modal_uv_cli.py`.

**Definition of Done:**

- `modal-uv run` works from nested repo directories.
- Foreground CLI prepares repo state before daemon use.
- Manifest building receives `sync.ignore`.
- Daemon lifecycle commands target the discovered repo.

---

### Task 10: Documentation And Skill Updates

**Files:**
- Modify: `README.md`
- Modify: `skills/use-modal-uv/SKILL.md`
- Modify: `modal-uv.yaml`
- Optionally add notes in docs if old copied specs are retained as historical documents

**Goal:** User-facing docs describe the new global CLI behavior and no longer recommend removed features.

**Pseudocode:**

```text
README should explain:
  install/run model for global CLI
  modal-uv.yaml discovery
  .modal-uv generated state and gitignore behavior
  sync.ignore config
  lazy deployment behavior
  supported commands
  no modal-uv py command

Skill should mirror README at a concise operational level.
```

**Steps:**

- [ ] Remove `modal-uv py` examples from README and skill.
- [ ] Remove `preload` examples from README, skill, and sample config.
- [ ] Document upward config discovery.
- [ ] Document `.modal-uv/` generated state and root `.gitignore` behavior.
- [ ] Document `sync.ignore`.
- [ ] Document lazy deployment and `pyproject.toml` redeploy trigger.
- [ ] Run `uv run ruff check .` to ensure docs changes did not expose lint issues through examples if checked.

**Definition of Done:**

- Docs match implemented command/config behavior.
- No current user-facing docs recommend `.s3-sync-ignore`, `modal-uv py`, or `preload`.

---

### Task 11: Full Verification

**Files:**
- No planned source changes unless verification reveals a defect.

**Goal:** Prove the implementation matches the approved spec and remains clean.

**Steps:**

- [ ] Run `uv run ruff check .`.
- [ ] Run `uv run ruff format --check .`.
- [ ] Run `uv run pytest`.
- [ ] Run `git status --short` and review changed files.
- [ ] Compare implementation against `docs/superpowers/specs/2026-07-06-modal-uv-global-cli-design.md` section by section.
- [ ] Confirm no production references remain for `.s3-sync-ignore`, `modal-uv py`, `preload`, `/spawn_python`, or `sync_and_run_python` except in historical copied design docs if intentionally retained.

**Definition of Done:**

- Ruff check passes.
- Ruff format check passes.
- Pytest passes.
- Changed files are intentional.
- Implementation satisfies the spec.

---

## Plan Self-Review

**Spec coverage:** Covered repo discovery, `.modal-uv/` state, root `.gitignore`, `sync.ignore`, `.s3-sync-ignore` removal, `py`/preload removal, detached-daemon Modal SDK boundary, lazy deployment, generated deployment artifact, fingerprint inputs, docs, and verification.

**Placeholder scan:** No unresolved placeholders are intended. Steps are goal and pseudocode based per user instruction, without explicit implementation code.

**Type consistency:** The plan consistently uses `repo_root`, `config_path`, `ProjectContext`, `TrackingConfig`, `sync.ignore`, `.modal-uv/`, `deployment.py`, and deployment fingerprint terminology across tasks.
