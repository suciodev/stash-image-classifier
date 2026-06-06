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

Progress and log lines go to **stdout** as newline-delimited JSON:
```
{"progress": 0.5}
{"type": "Info", "message": "Processing image 1 of 100"}
```

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

## Adding New Tagging Features

### Architecture pattern

Each new tag type maps to a new classifier class in `src/`. The existing `ImageClassifier` in `src/classifier.py` is the reference implementation — model loaded once at construction, single public method returning a bool or list of strings.

The pipeline in `main.py` currently hard-wires `has_person → tag "exclude"`. As new classifiers are added, this should evolve to a multi-tag loop:

```python
# Sketch — not current code
tags_to_apply = []
has_person = classifier.has_person(path)
if not has_person:
    tags_to_apply.append("exclude")
else:
    tags_to_apply.extend(clothing_classifier.classify(path))  # e.g. ["bikini"]
for tag in tags_to_apply:
    client.add_tag_to_image(image_id, client.find_or_create_tag(tag))
```

The same pattern applies in `run_hook` (per-image hook) and `scrapers/classify.py` (per-image scraper).

### Clothing tags (bikini, lingerie, underwear, etc.)

**Recommended approach: CLIP zero-shot classification**

CLIP compares an image against a list of text prompts and returns similarity scores. No training required — new categories are just new strings. `torch` is already a dependency, so the only addition is `transformers` (HuggingFace) or `openai-clip`.

```python
# src/clothing_classifier.py — sketch
from transformers import CLIPProcessor, CLIPModel
import torch

_LABELS = ["bikini or swimwear", "lingerie or underwear", "fully clothed", "nude"]
_MODEL_ID = "openai/clip-vit-base-patch32"   # ~600 MB, runs CPU-only

class ClothingClassifier:
    def __init__(self):
        self.model = CLIPModel.from_pretrained(_MODEL_ID)
        self.processor = CLIPProcessor.from_pretrained(_MODEL_ID)

    def classify(self, image_path: str) -> list[str]:
        """Returns tag names to apply (empty list = no clothing tag)."""
        from PIL import Image
        image = Image.open(image_path).convert("RGB")
        inputs = self.processor(text=_LABELS, images=image, return_tensors="pt", padding=True)
        with torch.no_grad():
            logits = self.model(**inputs).logits_per_image[0]
        probs = logits.softmax(dim=0)
        best_idx = probs.argmax().item()
        best_label = _LABELS[best_idx]
        if probs[best_idx] < 0.5:          # not confident enough
            return []
        if "bikini" in best_label or "swimwear" in best_label:
            return ["bikini"]
        if "lingerie" in best_label or "underwear" in best_label:
            return ["lingerie"]
        return []
```

**Key design decisions:**

- **Gate on person detection first.** Only run clothing classification when `has_person` is True — otherwise you'd tag an empty bikini on a hanger.
- **Prompt wording matters more than threshold tuning.** CLIP is sensitive to phrasing; test against fixtures before shipping. "a woman in a bikini" beats "bikini" as a prompt.
- **Model file handling.** CLIP downloads on first use via HuggingFace; for offline deployments, pre-download with `model.save_pretrained("./clip-vit-b32")` and load from that local path. Follow the same pattern as `yolov8n.pt` — bundle alongside the plugin.
- **Confidence threshold.** Start at 0.5 and tune downward using `tests/check_fixtures.py`-style validation against labelled examples before lowering.

**Alternative: attribute detection with a fashion YOLO model**

If CLIP accuracy is insufficient (e.g. pool scenes where swimwear vs. nude is ambiguous), consider a model fine-tuned on DeepFashion2. These exist as pre-trained YOLO checkpoints and would slot into `ImageClassifier`'s pattern with a different class list. Trade-off: less flexible (fixed label set), more accurate per-category.

### Adding fixtures for a new classifier

Add labelled samples under `tests/fixtures/<feature>/`:
```
tests/fixtures/clothing/
    bikini/       person_bikini_beach_01.jpg ...
    lingerie/     person_lingerie_studio_01.jpg ...
    clothed/      person_jeans_street_01.jpg ...
```

Then extend `tests/check_fixtures.py` with a validation loop for the new classifier, following the same pattern as the person detection check. Run with `uv run python -m tests.check_fixtures` before committing thresholds.

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
