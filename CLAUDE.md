# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A [Stash](https://github.com/stashapp/stash) plugin that classifies images using local ML inference and auto-applies tags. The initial use case: tag images where no person is the main subject with an "exclude" label, targeting Instagram media libraries.

The plugin ships three integration points:
1. **Bulk task** (`mode: classify`) — processes all images in a Stash library, run from the Tasks panel. Supports three variants: Classify All Images, Classify Untagged Images, and Recheck Exclude-Tagged Images.
2. **Auto-hook** (`Image.Create.Post`) — classifies each image as it is scanned into the library.
3. **Per-image scraper** (`imageByFragment`) — exposed in the image edit dialog; classifies one image on demand and proposes tags for the user to confirm.

Tags applied: `exclude` (no person, no NSFW content), `explicit`, `revealing`, `suggestive` (NSFW severity tiers from NudeNet body-part detection), `bikini`, `swimwear`, `lingerie`, `sportswear`, `dress` (clothing categories from CLIP zero-shot classification — applied only when a person is present; not mutually exclusive with NSFW tags).

## Development Commands

### Local unit tests

```bash
# Install dependencies (creates .venv automatically)
uv sync

# Run unit tests
uv run pytest

# Validate classifier accuracy against fixture images (not part of pytest)
uv run python -m tests.check_fixtures

# Lint / type check
uv run flake8 . --max-line-length=100
uv run mypy src/
```

### Dev Stash sandbox (port 9995)

The `dev-infra/` directory contains a fully isolated Stash instance for manual testing. It runs on port 9995 and never touches the production instances (9999/9998/9997).

```bash
# Deploy plugin + scraper to dev, then start the container (first run ~10 min — downloads torch)
make start-dev

# Re-deploy only (container already running)
make deploy-dev          # plugin only
make deploy-scraper-dev  # scraper only

# Tail logs
make logs-dev

# Stop
make stop-dev

# Force full image rebuild (e.g. after changing dev-infra/Dockerfile)
make rebuild-dev
```

**Fixture images** are mounted into the container at `/data/fixtures` (sourced from `tests/fixtures/person_detection/`). Add that path as a library in the Stash UI after first launch.

**Docker group:** If you see `permission denied: /var/run/docker.sock`, run `newgrp docker` (or close and reopen the WSL terminal to pick up the group permanently).

### Production deploy

```bash
# Plugin only (no model file — assumes yolov8n.pt is already deployed)
make deploy

# Plugin + model
make deploy-model

# Plugin + model + scraper
make deploy-all
```

Production paths point to `/mnt/b/SteamLibrary/.../stashdb/stash-common/{plugins,scrapers}/stash-image-classifier`. **Never run these unless explicitly deploying to production.**

**NudeNet production prerequisite:** `nudenet>=3.0` must be pip-installed in the production Stash container before the scraper can run. The ONNX model (`320n.onnx`, ~12 MB) is bundled inside the package — no separate model download is needed. Run `pip install "nudenet>=3.0,<4.0"` in the production environment once before first use.

### Simulate a plugin call locally

```bash
echo '{"server_connection":{"Scheme":"http","Host":"localhost","Port":9999},"args":{"mode":"classify"}}' | uv run python main.py
```

## Key Files

### Plugin

- `stash-image-classifier.yml` — Plugin manifest. Declares the bulk task and the `Image.Create.Post` hook.
- `main.py` — Entry point. Reads JSON from stdin, dispatches to `run_classify()` (bulk) or `run_hook()` (per-image auto).
- `src/classifier.py` — YOLOv8-based person detection with confidence and area thresholds. Model path is resolved relative to `__file__` so it works regardless of working directory.
- `src/nsfw_classifier.py` — NudeNet 640m ONNX body-part detector. Returns severity tags (`explicit`, `revealing`, `suggestive`). Runs unconditionally (YOLO misses unusual explicit poses).
- `src/clothing_classifier.py` — CLIP zero-shot clothing classifier. Returns category tags (`bikini`, `swimwear`, `lingerie`, `sportswear`, `dress`). Gated on person presence.
- `src/stash_client.py` — GraphQL client: `find_images`, `find_image_by_id`, `add_tag_to_image`, `find_or_create_tag`.
- `src/__init__.py` — `log(level, message)` and `progress(value)` helpers (write newline-delimited JSON to stdout per Stash protocol).

### Scraper

- `scrapers/stash-image-classifier.yml` — Scraper manifest. Declares `imageByFragment` pointing to `classify.py`.
- `scrapers/classify.py` — Standalone script invoked by Stash's scraper system. Reads image fragment JSON from stdin, imports `ImageClassifier` from the sibling plugin directory, returns `{"tags": [{"name": "exclude"}]}` or `{}`.

### Tests

- `tests/check_fixtures.py` — Manual accuracy check against labelled images in `tests/fixtures/{person_detection,nsfw,clothing}/`. Run directly with `make check-fixtures`.

### Dev infrastructure

- `dev-infra/Dockerfile` — Debian (python:3.12-slim) image with the official stash-linux binary + ultralytics added. See "Platform issues" below.
- `dev-infra/docker-compose.yml` — Dev container config: port 9995, fixture mount, runtime dirs.
- `dev-infra/stash-config.yml` — **Tracked** pre-seeded Stash config. Mounted as `/root/.stash/config.yml` inside the container to ensure `plugins_path` is set correctly. See ADR-002.

## Stash Plugin Architecture

Stash plugins are invoked as subprocess tasks. Stash passes JSON to the plugin via **stdin** and the plugin communicates back via **stdout** using the Stash task RPC protocol.

### Plugin manifest shape

```yaml
name: Image Classifier
exec:
  - python
  - "{pluginDir}/main.py"
interface: raw
tasks:
  - name: Classify Images
    defaultArgs:
      mode: classify
hooks:
  - name: Auto-classify on scan
    triggeredBy:
      - Image.Create.Post
```

**Important:** The `{pluginDir}` placeholder in `exec[1]` is required. Stash's plugin runner substitutes it with the absolute path to the plugin's directory at runtime. Without it, Stash does not prepend the plugin directory to the script argument, and the path construction falls back to a broken default that produces `//main.py`, causing a "No such file or directory" error. This is the convention used throughout CommunityScripts (e.g. `"{pluginDir}/phashDuplicateTagger.py"`).

### Plugin invocation (task)

```json
{
  "server_connection": { "Scheme": "http", "Host": "localhost", "Port": 9999, "SessionCookie": {...} },
  "args": { "mode": "classify" }
}
```

### Plugin invocation (hook)

```json
{
  "server_connection": { "Scheme": "http", "Host": "localhost", "Port": 9999, "SessionCookie": {...} },
  "args": {
    "mode": "Image.Create.Post",
    "hookContext": { "id": 123, "type": "Image.Create.Post" }
  }
}
```

Progress and log lines go to **stderr** using Stash's character-prefix protocol:
```
\x01p\x020.5                            # progress (float 0.0–1.0)
\x01i\x02Processing image 1 of 100      # info log
\x01e\x02Something went wrong           # error log
```
Level chars: `t`=trace, `d`=debug, `i`=info, `w`=warning, `e`=error, `p`=progress.

The `raw` interface reads all of **stdout** at once after the plugin exits and expects either a single JSON `PluginOutput` blob or plain text. Do not write structured per-line events to stdout.

### Scraper invocation (imageByFragment)

Stash serialises the current image data and passes it to the script on **stdin**. The script writes a JSON object with fields to update on **stdout**. No `server_connection` — the scraper UI handles applying the result.

```json
// stdin — image fragment (Stash sends metadata only; no file paths)
{ "id": "42", "title": "...", "urls": [], "url": null, ... }

// stdout — proposed updates
{ "tags": [{"name": "exclude"}] }
```

**Important:** Stash's `imageByFragment` fragment does not include file paths. `scrapers/classify.py` resolves the path by calling back to `http://localhost:{STASH_PORT}/graphql` using `findImage(id)`. `STASH_PORT` is set by Stash as an environment variable when running the scraper.

## Classification Approach

**Constraint: fully local and offline — no AI API calls, no token costs.**

Stack:
- `ultralytics` (YOLOv8n) — person detection; `yolov8n.pt` (~6 MB) is bundled alongside the plugin for fully-offline deployments.
- `nudenet` (NudeNet v3, 640m ONNX) — NSFW body-part detection; `640m.onnx` (~18 MB) is bundled alongside the plugin.
- `opencv-python-headless` — image loading (headless; no GUI deps)
- `requests` — Stash GraphQL API calls

### Detection thresholds

`ImageClassifier` (YOLOv8n) uses two thresholds:

- **`min_confidence` (default 0.60)** — passed directly to YOLO; filters low-confidence partial detections (blurred limbs, reflections).
- **`min_area_fraction` (default 0.05)** — post-inference; a box must cover ≥5% of image area to count. Filters small background figures.

`NsfwClassifier` (NudeNet 640m) uses one threshold:

- **`min_confidence` (default 0.25)** — minimum body-part detection score to count a detection. Lower values improve recall; raise if you see false positives on clothed subjects.

### NSFW classification pipeline

NsfwClassifier runs **unconditionally** (not gated on YOLO), because YOLOv8 misses people in unusual explicit poses (trained on COCO, not adult content). NSFW and clothing tags are not mutually exclusive — a lingerie image can receive both.

Tag mapping (NudeNet label → Stash tag):
- `FEMALE_GENITALIA_EXPOSED`, `MALE_GENITALIA_EXPOSED`, `ANUS_EXPOSED` → `explicit`
- `FEMALE_BREAST_EXPOSED`, `BUTTOCKS_EXPOSED` → `revealing`
- `FEMALE_BREAST_COVERED`, `FEMALE_GENITALIA_COVERED`, `BUTTOCKS_COVERED` → `suggestive`

### Clothing classification pipeline

ClothingClassifier runs only when a person is detected. CLIP zero-shot matches the image against 5 clothing prompts plus a catch-all; the highest-probability label above 0.4 threshold produces a tag.

Prompts and tags (see `src/clothing_classifier.py` for exact strings):
- bikini or two-piece swimwear → `bikini`
- one-piece swimsuit, bathing suit, or maillot → `swimwear`
- lingerie, lace underwear, or bra and panties set → `lingerie`
- exercising/at gym: athletic clothing, sports bra, or gym leggings → `sportswear`
- fashion dress, mini/cocktail/bodycon dress, skirt, or street style → `dress`
- catch-all (regular/casual clothes) → *(no tag)*

Tune `min_confidence` (default 0.4) using `tests/check_fixtures.py` against `tests/fixtures/clothing/`. See ADR-005.

Note: no negative fixtures (regular-clothed subjects) exist in `tests/fixtures/clothing/`. The reported accuracy measures recall only — precision on untagged subjects is untested. Add `clean/` fixtures before lowering the threshold further.

### Classification decision flow (`_classify_image` in `main.py`)

```
nsfw_tags  = NsfwClassifier.classify(path)    # unconditional
has_person = ImageClassifier.has_person(path)

if not has_person and not nsfw_tags → ["exclude"]
clothing_tags = ClothingClassifier.classify(path) if has_person else []
return nsfw_tags + clothing_tags               # may be empty []
```

### Known classifier limitations

- **Horizontal/submerged bodies in water** — YOLO is trained on COCO (dominated by upright people). Swimmers/floaters are frequently missed. NudeNet may catch these if explicit body parts are visible.
- **Digital illustrations and artwork** — all three models are trained on photographs; illustrated people and NSFW/clothing content not reliably detected.
- **Product-shot partial bodies** — a cropped hand or face in a product photo may trigger a YOLO false positive.
- **Cunnilingus angle blind spots** — certain camera angles during oral sex may not expose enough body-part area for NudeNet to detect; tracked as `xfail_` fixtures in `tests/fixtures/`.
- **Swimwear vs. nude in pool scenes** — CLIP may confuse a nude person in water with swimwear. If this is a problem, consider a fashion YOLO model (see ADR-005).

### Adding fixtures for a new classifier

Add labelled samples under `tests/fixtures/<feature>/` following the naming convention `{expected_tag}_{descriptive_scene}.{ext}`. Add `.gitkeep` to empty dirs. Extend `tests/check_fixtures.py` with a validation loop. Run with `uv run python -m tests.check_fixtures` before committing thresholds.

## Stash GraphQL API

The plugin interacts with Stash's local GraphQL endpoint at `http://HOST:PORT/graphql`.

Key operations:
- `findImages(filter: {...})` — paginate through the image library
- `findImage(id: $id)` — fetch a single image (used by the hook handler)
- `imageUpdate(input: {...})` — apply tags; always merges with existing tags to avoid clobbering them
- `findOrCreateTag(name: "exclude")` — get or create a tag by name

Authentication uses the `SessionCookie` from the connection JSON passed via stdin.

## Dev Infrastructure: Known Platform Issues

### PyTorch + musl (historical — resolved)

The dev container previously used `stashapp/stash:v0.27` (Alpine/musl) as its base. PyTorch's manylinux wheels are built against glibc and required three separate workarounds on musl. The dev container now uses `python:3.12-slim` (Debian/glibc) with the official `stash-linux` binary, which is statically linked and runs on any x86-64 Linux kernel. All musl compatibility patches have been removed. See ADR-001.

### `//main.py` — plugin exec path error

**Symptom:** Stash logs `python3: can't open file '//main.py': [Errno 2] No such file or directory` when running the plugin task or hook.

**Cause:** The exec list in the plugin YAML is missing the `{pluginDir}` placeholder. Stash's plugin runner only substitutes `{pluginDir}` explicitly — it does not automatically prepend the plugin directory to Python script arguments. Without it, the path construction falls back to a broken default that concatenates a bare `/` with the script name, producing `//main.py`.

**Fix:** Use `"{pluginDir}/main.py"` in exec[1]:
```yaml
exec:
  - python
  - "{pluginDir}/main.py"
```

### Stash config.yml ownership

**Symptom:** `plugins_path` is empty or missing after a fresh container start, which can cause related plugin resolution failures.

**Cause:** When Stash first starts with an empty config dir, it writes `/root/.stash/config.yml` with `plugins_path: ""`. Downstream effects include broken plugin discovery.

**Fix:** `dev-infra/stash-config.yml` is a tracked file mounted as `/root/.stash/config.yml` in the container, ensuring `plugins_path: /root/.stash/plugins` is always present. See ADR-002.

## Project Constraints

- **No AI APIs** — no calls to OpenAI, Anthropic, or any token-based service. Local model inference only.
- **Non-destructive** — the plugin only adds tags, never modifies or deletes image files.
- **Stash-compatible Python** — target Python 3.9+ (3.8 is EOL as of Oct 2024).
- **Production safety** — production Stash instances are at `B:\SteamLibrary\...\stashdb\`. Never run `make deploy` or `make deploy-all` without explicit intent to push to production.
