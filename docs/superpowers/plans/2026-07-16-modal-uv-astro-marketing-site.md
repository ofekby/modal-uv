# modal-uv Astro Marketing Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first-pass Astro marketing homepage for `modal-uv` that is static, GitHub Pages-ready, visually distinctive, and optimized for agent setup first, GitHub stars second, and manual install third.

**Architecture:** Add a focused `site/` Astro project inside the repository. Keep the first version to a single static homepage with small Astro components, one global stylesheet, no framework island, and a minimal client-side copy interaction for the agent setup CTA.

**Tech Stack:** Astro static output, plain Astro components, CSS, minimal browser JavaScript, GitHub Pages-compatible configuration.

---

## Spec References

- Design spec: `docs/superpowers/specs/2026-07-16-modal-uv-astro-marketing-site-design.md`
- README positioning and commands: `README.md`
- Existing brand/banner assets: `docs/assets/modal-uv-banner.svg`, `docs/assets/modal-uv-banner-1280x640.svg`, `docs/assets/modal-uv-banner-1280x640.png`
- Astro GitHub Pages guidance: configure `site`, `base`, and static output in `astro.config.mjs`

## Global Constraints

- Do not make the site text heavy. Each section should communicate one concrete outcome.
- Do not lead with “no repo restructure” or “no Modal app required.” Those are supporting details only.
- Do not use the phrase “remote field” in user-facing copy.
- Use the approved hero: `Local loop. Modal compute.`
- Use the approved conversion priority: copy agent prompt, star GitHub, install manually.
- Use the Agent GPU Session direction: an opencode-inspired coding-agent TUI transcript as the memorable visual device.
- Motion must be subtle and disabled for `prefers-reduced-motion: reduce`.
- The site must work on mobile and desktop.
- Keep source files focused and easy to expand into future SEO pages.
- Prefer static Astro and CSS. Do not add React, Vue, Svelte, or animation libraries for this first version.
- Do not include explicit implementation code in this plan. Implementation agents should derive code from the goal, DoD, constraints, pseudocode, and referenced spec.

## File Responsibilities

- Create `site/package.json`: local scripts and Astro dependency metadata for the marketing site.
- Create `site/astro.config.mjs`: static Astro configuration with GitHub Pages-compatible `site` and `base` values.
- Create `site/src/pages/index.astro`: single homepage composition, SEO metadata, component wiring, copy interaction script hook.
- Create `site/src/components/ComputeField.astro`: hero opencode-style TUI illustration showing the agent prompt, mocked loading states, GPU code, modal-uv run, error, fix, rerun, and success. Do not include an IDE-like sidebar in the hero.
- Create `site/src/components/CopyPrompt.astro`: agent setup prompt CTA and setup panel copy target.
- Create `site/src/components/UseCaseCard.astro`: reusable visual card for GPU tests, training, CUDA checks, artifacts/checkpoints.
- Create `site/src/components/CommandPanel.astro`: compact command/log surfaces for manual install, run, logs, and abort examples.
- Create `site/src/styles/global.css`: design tokens, typography, layout, responsive behavior, animation, reduced-motion rules, focus states.
- Optionally create `site/public/og-image.png`: only if an existing asset can be reused or adapted without expanding scope.
- Modify root `README.md`: add a small website development note only if useful after the site exists.
- Modify root `.gitignore`: add site-generated output if the selected Astro output path is not already covered by existing ignore rules.

---

## Task 1: Scaffold The Astro Site Shell

**Goal:** Create a minimal static Astro project under `site/` that builds locally and is configured for later GitHub Pages publishing.

**Files:**
- Create: `site/package.json`
- Create: `site/astro.config.mjs`
- Create: `site/src/pages/index.astro`
- Create: `site/src/styles/global.css`

**Definition Of Done:**
- `site/` has a valid Astro project structure.
- `npm install` or the chosen package manager install succeeds inside `site/`.
- `npm run build` succeeds inside `site/`.
- The generated page renders a placeholder homepage that imports `global.css`.
- Astro config is static and compatible with publishing at `https://ofekby.github.io/modal-uv/`.

- [ ] **Step 1: Create the site package metadata**

  Pseudocode:
  - Define the package as private.
  - Add scripts for `dev`, `build`, and `preview`.
  - Add Astro as the only runtime/dev dependency needed for the first version.

- [ ] **Step 2: Create Astro config for GitHub Pages**

  Pseudocode:
  - Define a static Astro config.
  - Set `site` to the GitHub Pages owner domain.
  - Set `base` to `/modal-uv` for repository Pages.
  - Keep output static.

- [ ] **Step 3: Create the placeholder homepage**

  Pseudocode:
  - Add document metadata for title and description.
  - Import the global stylesheet.
  - Render a simple heading matching the approved hero line.
  - Render a placeholder CTA area to verify layout and CSS are loading.

- [ ] **Step 4: Create initial global CSS tokens**

  Pseudocode:
  - Define CSS variables for the approved palette.
  - Set base body background, foreground, font smoothing, and default link color.
  - Add a visible focus style.

- [ ] **Step 5: Install and build**

  Run from `site/`: `npm install`

  Run from `site/`: `npm run build`

  Expected: Astro completes a static build without errors.

- [ ] **Step 6: Commit the scaffold**

  Commit message: `Add Astro marketing site scaffold`

---

## Task 2: Implement The Visual System And Hero Composition

**Goal:** Build the distinctive first-screen experience around `Local loop. Modal compute.` and the opencode-style Agent GPU Session visual.

**Files:**
- Create: `site/src/components/ComputeField.astro`
- Modify: `site/src/pages/index.astro`
- Modify: `site/src/styles/global.css`

**Definition Of Done:**
- The hero uses the approved headline and outcome-focused subcopy.
- The TUI chat session visual appears in the hero on desktop and remains legible on mobile.
- The visual includes the full agent loop: user prompt, mocked loading states, agent writes GPU code, runs with `modal-uv`, hits an error, fixes code, reruns, and succeeds.
- Animation is subtle and disabled under reduced motion.
- The hero has the three conversion surfaces: copy prompt, GitHub star, install command snippet.

- [ ] **Step 1: Define the hero information hierarchy**

  Pseudocode:
  - Top label communicates ML/GPU and agentic development.
  - Main headline uses the two-line approved hero.
  - Subcopy names on-demand GPUs, long-running jobs, logs, aborts, and persistent artifacts.
  - Primary action says `Copy agent setup prompt`.
  - Secondary action says `Star on GitHub`.
  - Tertiary command line shows the manual install entry point.

- [ ] **Step 2: Build the ComputeField component**

  Pseudocode:
- Use semantic markup for a TUI-styled chat transcript.
- Represent the loop as prompt, code, modal-uv run, remote error, fix, rerun success.
- Use Modal Mint for user/setup moments, uv Violet for agent/code moments, Artifact Lime for success, and Field Blue for Modal run details.
- Keep chat labels short and concrete.

- [ ] **Step 3: Add subtle motion**

  Pseudocode:
- Animate chat rows into view subtly.
- Avoid chat bubbles that jump, shake, or feel like a full simulator.
- Add reduced-motion rules that freeze reveal animations.

- [ ] **Step 4: Apply responsive layout**

  Pseudocode:
- Desktop: split hero into text/CTA column and chat-session visual column.
- Mobile: stack text first, then a compact chat session.
  - Ensure CTAs remain above the fold on typical mobile screens.

- [ ] **Step 5: Build and visually inspect**

  Run from `site/`: `npm run build`

  Run from `site/`: `npm run preview`

  Expected: static build succeeds; hero is legible and visually distinct at desktop and mobile widths.

- [ ] **Step 6: Commit the hero**

  Commit message: `Build marketing site hero and compute field`

---

## Task 3: Add Conversion Interactions And Setup Panel

**Goal:** Make the primary agent setup CTA useful, with copy behavior and a compact manual install path.

**Files:**
- Create: `site/src/components/CopyPrompt.astro`
- Create: `site/src/components/CommandPanel.astro`
- Modify: `site/src/pages/index.astro`
- Modify: `site/src/styles/global.css`

**Definition Of Done:**
- Primary CTA copies the approved agent setup prompt to the clipboard.
- Copy success is visible to sighted users and announced through accessible text.
- If clipboard copy fails, the prompt remains visible and selectable.
- Manual install commands are visible in a compact setup panel.
- GitHub and PyPI links are present.

- [ ] **Step 1: Define the copy prompt component behavior**

  Pseudocode:
  - Render a button for copying the setup prompt.
  - Store the approved prompt text in the component or page as plain text.
  - On click, attempt clipboard write.
  - On success, update status text to `Copied setup prompt`.
  - On failure, update status text to tell the user to select the prompt manually.

- [ ] **Step 2: Add the setup panel content**

  Pseudocode:
  - Show the agent prompt in a compact, readable block.
  - Show manual commands separately from the agent prompt.
  - Keep command labels functional: install, onboard, initialize, run GPU test.

- [ ] **Step 3: Add command panels for observable jobs**

  Pseudocode:
  - Show examples for `modal-uv run`, `modal-uv logs`, and `modal-uv abort`.
  - Include an execution ID treatment to make long-running jobs feel tangible.
  - Avoid turning this into full documentation.

- [ ] **Step 4: Style conversion elements**

  Pseudocode:
  - Primary CTA uses Modal Mint and strong contrast.
  - GitHub star action is secondary but visible.
  - Manual install is tertiary and compact.
  - Focus states are visible and consistent.

- [ ] **Step 5: Build and interaction-check**

  Run from `site/`: `npm run build`

  In local preview, verify:
  - Copy button updates status after click.
  - Keyboard focus reaches copy, GitHub, PyPI, and install controls.
  - Manual prompt remains readable without JavaScript.

- [ ] **Step 6: Commit conversion interactions**

  Commit message: `Add setup prompt conversion panel`

---

## Task 4: Add Outcome Sections For ML/GPU And Agentic Use Cases

**Goal:** Add concise, visual sections that explain the concrete benefits without making the homepage read like docs.

**Files:**
- Create: `site/src/components/UseCaseCard.astro`
- Modify: `site/src/pages/index.astro`
- Modify: `site/src/styles/global.css`

**Definition Of Done:**
- Use-case cards cover GPU tests, model training, CUDA checks, and artifacts/checkpoints.
- Agent-native loop section shows edit, run on Modal, read logs, debug, rerun.
- Long jobs/artifacts section explains execution IDs, logs, aborts, and persistent volumes.
- Sections use short copy and visual structure instead of dense paragraphs.
- No section leads with repo-structure messaging.

- [ ] **Step 1: Define use-case card content**

  Pseudocode:
  - GPU tests: run hardware-dependent tests without blocking local iteration.
  - Model training: launch longer training scripts and keep the command shape familiar.
  - CUDA checks: verify GPU/CUDA behavior on Modal hardware.
  - Artifacts/checkpoints: persist outputs in Modal Volumes for future runs.

- [ ] **Step 2: Implement reusable card structure**

  Pseudocode:
  - Card receives label, title, short body, and command/example metadata.
  - Card markup remains semantic and scan-friendly.
  - Visual accents encode the use case using the approved color tokens.

- [ ] **Step 3: Add the agent-native loop section**

  Pseudocode:
  - Present the loop as edit, run, logs, debug, rerun.
  - Show a small trace of changed files, spawned execution ID, logs command, and rerun.
  - Keep the copy focused on acceleration for agents and human operators.

- [ ] **Step 4: Add long jobs and artifacts section**

  Pseudocode:
  - Explain that long jobs return execution IDs.
  - Show logs and abort as operational controls.
  - Show volume artifacts/checkpoints as durable outputs.

- [ ] **Step 5: Build and review content density**

  Run from `site/`: `npm run build`

  Expected: homepage remains visual and scannable; no section becomes a documentation wall.

- [ ] **Step 6: Commit outcome sections**

  Commit message: `Add ML GPU and agentic use case sections`

---

## Task 5: Add SEO, Metadata, And GitHub Pages Readiness

**Goal:** Prepare the static site for publishing and later SEO work without adding a full content system yet.

**Files:**
- Modify: `site/src/pages/index.astro`
- Modify: `site/astro.config.mjs`
- Modify: `site/package.json`
- Optionally create: `site/public/og-image.png`
- Optionally modify: `README.md`

**Definition Of Done:**
- Page title is clear and under common social preview limits.
- Meta description reflects the approved positioning.
- Canonical URL resolves correctly with the GitHub Pages base path.
- Open Graph and Twitter metadata exist.
- README includes site development commands if useful.
- Build output remains static.

- [ ] **Step 1: Add homepage metadata**

  Pseudocode:
  - Title should be concise, such as `modal-uv | Local loop. Modal compute.`
  - Description should mention Modal compute, ML/GPU projects, agents, logs, aborts, and artifacts in one short sentence.
  - Add canonical URL using the configured Astro site/base.
  - Add Open Graph and Twitter card fields.

- [ ] **Step 2: Add optional social image**

  Pseudocode:
  - Prefer reusing the existing 1280x640 banner if it fits the site identity.
  - If reused, place it where Astro can serve it statically.
  - If not reused, skip instead of creating a separate asset workflow in this task.

- [ ] **Step 3: Confirm GitHub Pages base behavior**

  Pseudocode:
  - Ensure generated asset URLs include `/modal-uv/` when needed.
  - Ensure local development remains usable.
  - Note any future custom-domain change needed if the site moves off repository Pages.

- [ ] **Step 4: Add README site commands if helpful**

  Pseudocode:
  - Add a short maintainer-only note for running the site locally.
  - Do not let website maintenance content distract from the package README.

- [ ] **Step 5: Build and inspect generated output**

  Run from `site/`: `npm run build`

  Expected: static output includes the homepage, assets, metadata, and no server-only routes.

- [ ] **Step 6: Commit metadata and Pages readiness**

  Commit message: `Prepare marketing site for GitHub Pages`

---

## Task 6: Final Verification And Polish Pass

**Goal:** Verify build quality, accessibility basics, responsive behavior, and repository cleanliness before presenting the site.

**Files:**
- Modify only files that need polish based on verification findings.

**Definition Of Done:**
- Astro build passes.
- The Python package tests are not broken by the website addition.
- The site is usable at mobile and desktop widths.
- Keyboard focus is visible and logical.
- Reduced motion is respected.
- Worktree contains only intended files.
- The implementation is ready for review and later GitHub Pages workflow setup.

- [ ] **Step 1: Run site build**

  Run from `site/`: `npm run build`

  Expected: build succeeds.

- [ ] **Step 2: Preview and manually inspect**

  Run from `site/`: `npm run preview`

  Inspect:
  - Desktop hero and sections.
  - Mobile hero and sections.
  - Copy prompt behavior.
  - Keyboard navigation.
  - Reduced-motion behavior.

- [ ] **Step 3: Run existing project verification**

  Run from repo root: `uv run ruff check .`

  Run from repo root: `uv run ty check`

  Run from repo root: `uv run pytest -q`

  Expected: existing Python checks pass or any failures are clearly unrelated and documented.

- [ ] **Step 4: Check git status and diff**

  Run from repo root: `git status --short`

  Run from repo root: `git diff --stat`

  Expected: only intended site, docs, and optional README/gitignore changes remain.

- [ ] **Step 5: Final polish commit**

  Commit message: `Polish Astro marketing site`

---

## Plan Self-Review

- Spec coverage: The plan covers the single Astro homepage, Agent GPU Session visual, conversion priority, copy prompt, GitHub star action, manual install, ML/GPU use cases, agentic loop, long jobs, artifacts, GitHub Pages readiness, accessibility, mobile behavior, and reduced motion.
- Placeholder scan: No `TBD`, `TODO`, or deferred implementation placeholders remain. Optional OG image reuse is explicitly bounded and can be skipped without blocking the first version.
- Type consistency: File names and component responsibilities are consistent across tasks. No framework island or extra animation dependency is introduced.
- User constraint check: This plan intentionally avoids explicit implementation code and uses goals, DoD, constraints, spec references, commands, and pseudocode-level guidance.
