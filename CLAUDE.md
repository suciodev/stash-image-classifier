# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A [Stash](https://github.com/stashapp/stash) plugin that classifies images using local ML inference and auto-applies tags. The initial use case: tag images where no person is the main subject with an "exclude" label, targeting Instagram media libraries.

The plugin ships two integration points:
1. **Bulk task** (`mode: classify`) — processes all images in a Stash library, run from the Tasks panel.
2. **Auto-hook** (`Image.Create.Post`) — classifies each image as it is scanned into the library.
3. **Per-image scraper** (`imageByFragment`) — exposed in the image edit dialog; classifies one image on demand and proposes the `exclude` tag for the user to confirm.

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

### Simulate a plugin call locally

```bash
echo '{"server_connection":{"Scheme":"http","Host":"localhost","Port":9999},"args":{"mode":"classify"}}' | uv run python main.py
```

## Key Files

### Plugin

- `stash-image-classifier.yml` — Plugin manifest. Declares the bulk task and the `Image.Create.Post` hook.
- `main.py` — Entry point. Reads JSON from stdin, dispatches to `run_classify()` (bulk) or `run_hook()` (per-image auto).
- `src/classifier.py` — YOLOv8-based person detection with confidence and area thresholds. Model path is resolved relative to `__file__` so it works regardless of working directory.
- `src/stash_client.py` — GraphQL client: `find_images`, `find_image_by_id`, `add_tag_to_image`, `find_or_create_tag`.
- `src/__init__.py` — `log(level, message)` and `progress(value)` helpers (write newline-delimited JSON to stdout per Stash protocol).

### Scraper

- `scrapers/stash-image-classifier.yml` — Scraper manifest. Declares `imageByFragment` pointing to `classify.py`.
- `scrapers/classify.py` — Standalone script invoked by Stash's scraper system. Reads image fragment JSON from stdin, imports `ImageClassifier` from the sibling plugin directory, returns `{"tags": [{"name": "exclude"}]}` or `{}`.

### Tests

- `tests/check_fixtures.py` — Manual accuracy check against labelled images in `tests/fixtures/person_detection/{include,exclude}/`. Run directly with `make check-fixtures`.

### Dev infrastructure

- `dev-infra/Dockerfile` — Alpine-based Stash image with Python + ultralytics added. See "Platform issues" below.
- `dev-infra/docker-compose.yml` — Dev container config: port 9995, fixture mount, runtime dirs.
- `dev-infra/stash-config.yml` — **Tracked** pre-seeded Stash config. Mounted as `/root/.stash/config.yml` inside the container to ensure `plugins_path` is set correctly. See ADR-002.

## Stash Plugin Architecture

Stash plugins are invoked as subprocess tasks. Stash passes JSON to the plugin via **stdin** and the plugin communicates back via **stdout** using the Stash task RPC protocol.

### Plugin manifest shape

```yaml
name: Image Classifier
exec:
  - python
  - main.py
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

Progress and log lines go to **stdout** as newline-delimited JSON:
```
{"progress": 0.5}
{"type": "Info", "message": "Processing image 1 of 100"}
```

### Scraper invocation (imageByFragment)

Stash serialises the current image data and passes it to the script on **stdin**. The script writes a JSON object with fields to update on **stdout**. No `server_connection` — the scraper UI handles applying the result.

```json
// stdin — image fragment (field names Stash sends)
{ "files": [{"path": "/data/fixtures/...jpg"}], "tags": [...], ... }

// stdout — proposed updates
{ "tags": [{"name": "exclude"}] }
```

`scrapers/classify.py` tries `files[].path`, then `visual_files[].path` (GraphQL shape), then `url` as fallbacks to handle any Stash version differences.

## Classification Approach

**Constraint: fully local and offline — no AI API calls, no token costs.**

Stack:
- `ultralytics` (YOLOv8n) — person detection; `yolov8n.pt` (~6 MB) is bundled alongside the plugin for fully-offline deployments.
- `opencv-python-headless` — image loading (headless; no GUI deps)
- `requests` — Stash GraphQL API calls

### Detection thresholds

`ImageClassifier` uses two thresholds:

- **`min_confidence` (default 0.60)** — passed directly to YOLO; filters low-confidence partial detections (blurred limbs, reflections).
- **`min_area_fraction` (default 0.05)** — post-inference; a box must cover ≥5% of image area to count. Filters small background figures.

Both are constructor arguments and can be tuned per deployment.

### Known classifier limitations

- **Horizontal/submerged bodies in water** — YOLO is trained on COCO (dominated by upright people). Swimmers/floaters are frequently missed.
- **Digital illustrations and artwork** — model trained on photographs; illustrated people not reliably detected.
- **Product-shot partial bodies** — hand, arm, or cropped face in a product photo may trigger a false positive.

## Stash GraphQL API

The plugin interacts with Stash's local GraphQL endpoint at `http://HOST:PORT/graphql`.

Key operations:
- `findImages(filter: {...})` — paginate through the image library
- `findImage(id: $id)` — fetch a single image (used by the hook handler)
- `imageUpdate(input: {...})` — apply tags; always merges with existing tags to avoid clobbering them
- `findOrCreateTag(name: "exclude")` — get or create a tag by name

Authentication uses the `SessionCookie` from the connection JSON passed via stdin.

## Dev Infrastructure: Known Platform Issues

### Alpine + PyTorch: missing `pthread_attr_setaffinity_np`

**Symptom:** `OSError: Error relocating .../torch/lib/libgomp-*.so.1: pthread_attr_setaffinity_np: symbol not found` when importing ultralytics/torch.

**Cause:** PyTorch's bundled `libgomp` was compiled against glibc and references `pthread_attr_setaffinity_np` (a GNU extension for CPU affinity). Alpine's musl libc doesn't provide it, and `gcompat` doesn't stub it.

**Fix:** The Dockerfile compiles a one-line no-op stub and sets `ENV LD_PRELOAD` to load it before any Python process starts. See `dev-infra/Dockerfile` and ADR-001.

### Stash config.yml ownership

**Symptom:** Plugin manifest runs with `//main.py` as the script path (double slash), causing "no such file" errors.

**Cause:** When Stash first starts with an empty config dir, it writes `/root/.stash/config.yml` owned by root. If `plugins_path` is missing or empty in that file, Stash constructs the plugin path as `"/" + "/" + "main.py"`.

**Fix:** `dev-infra/stash-config.yml` is a tracked file mounted as `/root/.stash/config.yml` in the container, ensuring `plugins_path: /root/.stash/plugins` is always present. See ADR-002.

## Project Constraints

- **No AI APIs** — no calls to OpenAI, Anthropic, or any token-based service. Local model inference only.
- **Non-destructive** — the plugin only adds tags, never modifies or deletes image files.
- **Stash-compatible Python** — target Python 3.9+ (3.8 is EOL as of Oct 2024).
- **Production safety** — production Stash instances are at `B:\SteamLibrary\...\stashdb\`. Never run `make deploy` or `make deploy-all` without explicit intent to push to production.
