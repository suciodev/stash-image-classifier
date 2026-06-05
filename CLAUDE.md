# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A [Stash](https://github.com/stashapp/stash) plugin that classifies images using local ML inference and auto-applies tags. The initial use case: tag images where no person is the main subject with an "exclude" label, targeting Instagram media libraries.

## Development Commands

```bash
# Install dependencies (creates .venv automatically)
uv sync

# Run unit tests
uv run pytest

# Run a single test
uv run pytest tests/test_classifier.py::test_returns_false_for_missing_file

# Validate classifier accuracy against fixture images
uv run python -m tests.check_fixtures

# Lint
uv run flake8 . --max-line-length=100

# Type check
uv run mypy src/

# Add a new dependency
uv add <package>

# Run plugin manually (simulates Stash calling it)
echo '{"server_connection":{"Scheme":"http","Host":"localhost","Port":9999},"args":{"mode":"classify"}}' | uv run python main.py
```

## Stash Plugin Architecture

Stash plugins are invoked as subprocess tasks. Stash passes JSON to the plugin via **stdin** and the plugin communicates back via **stdout** using the Stash task RPC protocol. The plugin declares itself via a YAML manifest.

### Key Files

- `stash-image-classifier.yml` — Plugin manifest. Declares task modes, the exec command, and required permissions.
- `main.py` — Entry point. Reads JSON from stdin, dispatches to task handlers.
- `src/classifier.py` — YOLOv8-based person detection with confidence and area thresholds.
- `src/stash_client.py` — GraphQL client for querying images and applying tags via the Stash API.
- `tests/check_fixtures.py` — Manual accuracy check against labelled images in `tests/fixtures/person_detection/{include,exclude}/`. Not part of the pytest suite; run directly to validate real-world performance.

### Plugin Manifest Shape

```yaml
name: Image Classifier
description: Classifies images and applies tags using local ML inference
url: https://github.com/suciodev/stash-image-classifier
version: 0.1.0
exec:
  - python
  - main.py
interface: raw
tasks:
  - name: Classify Images
    description: Detect persons and apply exclude tags to images without people
    defaultArgs:
      mode: classify
```

### Communication Protocol

Main receives input like:
```json
{
  "server_connection": { "Scheme": "http", "Host": "localhost", "Port": 9999, "SessionCookie": {...} },
  "args": { "mode": "classify" }
}
```

Progress and log lines go to **stdout** as newline-delimited JSON:
```
{"progress": 0.5}
{"type": "Info", "message": "Processing image 1 of 100"}
```

## Classification Approach

**Constraint: fully local and offline — no AI API calls, no token costs.** Local neural network inference is fine.

Stack:
- `ultralytics` (YOLOv8n) — person detection; model (~6MB) downloads once on first run then lives in the project root. Bundle `yolov8n.pt` alongside the plugin for fully-offline deployments.
- `opencv-python` — image loading
- `requests` — Stash GraphQL API calls

### Detection Logic

`ImageClassifier` in `src/classifier.py` uses two thresholds to distinguish "person is the subject" from "person appears incidentally":

- **`min_confidence` (default 0.60)** — passed directly to YOLO; boxes below this are discarded before our code sees them. Filters low-confidence partial detections (blurred limbs, reflections).
- **`min_area_fraction` (default 0.05)** — post-inference; a box must cover ≥5% of image area to count. Filters small background figures.

Both thresholds are constructor arguments and can be tuned per deployment.

### Known Classifier Limitations

These failure modes were identified during fixture testing and are not fixable by threshold tuning alone:

- **Horizontal/submerged bodies in water** — YOLO is trained on COCO which is dominated by upright standing people. People swimming, floating, or viewed from behind in water are frequently missed.
- **Digital illustrations and artwork** — The model is trained on photographs; illustrated people are not reliably detected.
- **Product-shot partial bodies** — When only a hand, arm, or cropped face is visible as a prop in a product photo, YOLO may detect a person with high confidence and area despite the person not being the primary subject.

## Stash GraphQL API

The plugin interacts with Stash's local GraphQL endpoint at `http://HOST:PORT/graphql`.

Key operations:
- `findImages(filter: {...})` — paginate through the image library
- `imageUpdate(input: {...})` — apply tags to an image; always reads existing tags first to avoid clobbering them
- `findOrCreateTag(name: "exclude")` — get or create a tag by name

Authentication uses the `SessionCookie` from the connection JSON passed via stdin.

## Project Constraints

- **No AI APIs** — no calls to OpenAI, Anthropic, or any token-based service. Local model inference is fine.
- **Non-destructive** — the plugin only adds tags, never modifies or deletes image files.
- **Stash-compatible Python** — target Python 3.9+ (3.8 is EOL as of Oct 2024).
