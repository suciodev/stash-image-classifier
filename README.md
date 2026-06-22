# stash-image-classifier

A [Stash](https://github.com/stashapp/stash) plugin that classifies images using local ML inference and auto-applies tags. The initial use case: tag images where no person is the main subject with an `exclude` label — useful for filtering Instagram media libraries.

All inference runs locally. No external AI API calls, no token costs.

## How it works

Two models run on every image:

- **YOLOv8n** — detects whether a person is present (COCO-trained, ~6 MB model)
- **NudeNet 640m** — detects exposed body parts and classifies NSFW severity (~18 MB ONNX model)

Tags applied:

| Tag | When |
|---|---|
| `exclude` | No person detected AND no NSFW content detected |
| `explicit` | Genitalia or anus exposed |
| `revealing` | Breasts or buttocks exposed |
| `suggestive` | Covered intimate areas detected |

NudeNet runs unconditionally (not gated on YOLO) because YOLOv8 misses people in unusual explicit poses. If any NSFW body parts are detected, NSFW tags take priority and `exclude` is not applied.

## Integration points

| Integration | How to use |
|---|---|
| **Classify All Images** | Tasks panel → run once to tag the entire library |
| **Classify Untagged Images** | Tasks panel → skips images already carrying any classifier tag; safe to re-run after adding new images |
| **Recheck Exclude-Tagged Images** | Tasks panel → re-runs only `exclude`-tagged images; useful after threshold tuning |
| **Auto-hook** | Fires on `Image.Create.Post` — classifies each image as it is scanned |
| **Per-image scraper** | Image edit dialog → "Scrape with Image Classifier" — classifies one image on demand |

## Installation

1. Copy the plugin directory to your Stash plugins folder:
   ```
   <stash-config>/plugins/stash-image-classifier/
   ```
2. Copy the scraper directory to your Stash scrapers folder:
   ```
   <stash-config>/scrapers/stash-image-classifier/
   ```
3. Ensure `python` (3.9+) is on the path with `ultralytics`, `nudenet>=3.0`, `opencv-python-headless`, and `requests` installed.
4. The model files must be present in the plugin directory for fully-offline use:
   - `yolov8n.pt` (~6 MB) — YOLOv8 person detection
   - `640m.onnx` (~18 MB) — NudeNet body-part detection
   If absent, the models will attempt to download on first run.
5. Reload plugins in Stash (Settings → Plugins → Reload).

## Development

See [CLAUDE.md](CLAUDE.md) for the full development guide, including:
- Local test commands
- Dev Stash sandbox setup (`make start-dev`, port 9995)
- Dev container setup and known platform notes
- GraphQL API reference
- Stash raw plugin protocol details

Quick start:
```bash
uv sync           # install deps
uv run pytest     # unit tests
make start-dev    # spin up isolated dev Stash on port 9995
```

## Known limitations

- **Swimmers / submerged bodies** — YOLO (trained on COCO) misses people lying horizontal or underwater. NudeNet may catch these if explicit content is visible.
- **Illustrations / artwork** — both models are trained on photographs; illustrated content is not reliably detected.
- **Product shots with partial bodies** — a cropped hand or face in a product photo may trigger a YOLO false positive.
- **Cunnilingus angle blind spots** — certain camera angles may not expose enough body-part area for NudeNet to detect; these are tracked as `xfail_` fixtures.

## License

MIT
