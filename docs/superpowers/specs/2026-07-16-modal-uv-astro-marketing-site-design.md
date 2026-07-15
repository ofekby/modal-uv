# modal-uv Astro Marketing Site Design

## Goal

Create the first marketing website for `modal-uv`, publishable later on GitHub Pages. The site should convert visitors into trying `modal-uv`, starring the repository, and using the agent setup flow. It should be visually distinctive, not text heavy, and should establish a strong base for future SEO pages.

## Audience

Primary audience: ML and GPU developers who need Modal compute for tests, training, CUDA checks, long-running jobs, checkpoints, and artifacts.

Secondary audience: humans operating coding agents who want the agent to run GPU-heavy work, inspect logs, abort work, debug failures, and rerun without manual Modal ceremony.

## Conversion Priority

The homepage conversion order is:

1. Copy the coding-agent setup prompt.
2. Star the GitHub repository.
3. Install and try `modal-uv` manually.

The primary hero CTA copies a short agent setup prompt. The GitHub star action is visually present as the next-best action. Manual install remains available in a compact setup panel and command snippet.

## Positioning

The page should sell what `modal-uv` enables out of the box, not the implementation detail that users do not need to restructure their repo. Avoid centering copy on “normal repo” or “no Modal app required” as the lead promise. Those details can appear later as supporting context.

Hero headline:

```text
Local loop.
Modal compute.
```

Hero subcopy:

```text
Give ML projects and coding agents on-demand GPUs, long-running jobs, logs, aborts, and persistent artifacts from one command.
```

Supporting hero line:

```text
Run GPU tests, training scripts, CUDA checks, and checkpoint-producing jobs on Modal while your agent keeps the edit-run-debug loop moving.
```

Core section headlines:

- `Give your agent a GPU lane`
- `Run the work your laptop should not`
- `Keep long jobs observable`
- `Artifacts land where the next run can find them`
- `Start with one copied prompt`

## Visual Direction

Direction name: Agent GPU Session.

The site should feel like watching a coding agent use Modal compute inside an opencode-style terminal TUI: session chrome, workspace/tool context, user prompt, agent writes GPU-related code, agent runs it with `modal-uv`, the remote run hits an error, the agent fixes the code, reruns, and succeeds.

This is the primary aesthetic risk: the hero visual is an animated coding-agent TUI instead of a conventional product screenshot or terminal-only block. It makes the agent-native behavior concrete and shows why remote GPU access matters: the agent can run, observe, fix, and rerun without the human becoming the bridge.

Do not call the concept “remote field” in user-facing copy. Use direct language such as `Modal compute`, `GPU lane`, `long jobs`, `logs`, `artifacts`, and `one command`.

## Design Tokens

Colors:

- `Void Graphite #080B12`: page background
- `Panel Ink #101725`: cards, nav, and command surfaces
- `Modal Mint #7BFFB2`: primary CTA and active paths
- `uv Violet #DE5FE9`: uv and agent accents
- `Artifact Lime #D7FF64`: checkpoints, volumes, and successful output
- `Field Blue #6DA7FF`: Modal compute glow and secondary path accents

Typography:

- Display: `Space Grotesk` or `Geist`, tight tracking, large line-height, restrained use.
- Body: `Inter` or `Source Sans 3`, readable marketing copy.
- Utility: `JetBrains Mono`, for commands, execution IDs, chat labels, and system states.

Type treatment:

- Hero headline uses short stacked lines with high contrast and tight spacing.
- Mono labels encode chat and system state, such as `USER PROMPT`, `AGENT WRITES CODE`, `REMOTE ERROR`, and `RERUN SUCCEEDS`.
- Copy should be concrete and short. Avoid generic phrases like “supercharge your workflow.”

## Page Structure

The first version is a single Astro homepage.

```text
[nav]
modal-uv | Use cases | Agent setup | GitHub

[hero]
Local loop.
Modal compute.
Short outcome-focused subcopy.
Primary CTA: Copy agent setup prompt.
Secondary CTA: Star on GitHub.
Tertiary install command snippet.
Chat-like agent session illustration.

[use cases]
GPU tests | model training | CUDA checks | artifacts/checkpoints

[agent-native loop]
Edit -> run on Modal -> read logs -> debug -> rerun
Show execution ID, logs command, abort command, and changed-file sync.

[long jobs and artifacts]
Explain execution IDs, observable jobs, aborts, and persistent Modal Volumes.

[setup panel]
Copyable agent prompt plus manual install commands.

[footer]
Copy prompt | GitHub | PyPI | License
```

## Motion

Motion should be subtle, not a scroll-heavy demo.

- The hero TUI animates the agent loop in sequence: prompt, code, run, error, fix, success.
- Section reveals use small opacity and translate transitions.
- Hover states should feel like map nodes activating, not generic card lift everywhere.
- `prefers-reduced-motion: reduce` disables path animation and reveal transitions.

## Content Requirements

Primary agent prompt copy target:

```text
Install modal-uv globally and set it up:
1. Run: pip install modal-uv
2. Run: modal-uv onboard
3. In the project repo, run: modal-uv init
4. Edit modal-uv.yaml for GPU, timeout, and volumes
5. Run: modal-uv doctor
6. Use modal-uv run -- <uv command> or modal-uv exec -- <shell command>
```

Manual install commands:

```bash
pip install modal-uv
modal-uv onboard
modal-uv init
modal-uv run -- pytest -m gpu
```

Observable job commands:

```bash
modal-uv logs fc-...
modal-uv abort fc-...
```

## Technical Shape

Use Astro as a static site in the repository, suitable for GitHub Pages. The initial implementation should keep the site small and easy to expand.

Expected structure:

```text
site/
  astro.config.mjs
  package.json
  src/
    pages/index.astro
    styles/global.css
    components/
      ComputeField.astro
      CopyPrompt.astro
      UseCaseCard.astro
      CommandPanel.astro
```

The first version can use plain Astro, CSS, and a small inline script for copying the agent prompt. Avoid introducing a framework island unless the copy interaction or animation clearly needs it.

For GitHub Pages, configure Astro with a base path compatible with publishing under `ofekby.github.io/modal-uv` if needed. If the repository later gets a custom domain, the base path can be revisited.

## Accessibility And Quality

- CTAs must be keyboard reachable with visible focus states.
- Copy buttons should report success text, such as `Copied setup prompt`.
- Motion must respect reduced-motion preferences.
- Color contrast must remain readable on dark backgrounds.
- The page must work on desktop and mobile.
- The design should stay visual, but important claims must remain text so search engines can index them.

## Future SEO Expansion

The homepage should leave room for later pages, but those pages are out of scope for the first implementation. Likely future pages:

- GPU tests on Modal from `uv`
- Agentic ML development with Modal GPUs
- Persistent artifacts and checkpoints with Modal Volumes
- Running CUDA checks remotely

## Out Of Scope For First Version

- Blog system
- Documentation migration from README
- Live GitHub star count
- Full interactive command simulator
- User analytics
- Multi-page SEO content
