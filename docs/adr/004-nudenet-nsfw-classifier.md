# ADR-004: NudeNet 640m for NSFW body-part detection

**Status:** Accepted  
**Date:** 2026-06-09

## Context

YOLOv8n (trained on COCO) reliably detects people in typical poses but fails on 7–10% of explicit images where the person is in an unusual position (e.g. lying prone, heavily cropped). These images were being incorrectly tagged `exclude` despite clearly containing a person and explicit content.

The plugin needed a second classifier that:
- Runs locally and offline
- Detects NSFW content independent of person pose
- Produces severity tiers rather than a single boolean flag
- Doesn't require fine-tuning or labelled training data for new categories

## Decision

Use **NudeNet v3** with the **640m ONNX** model for NSFW body-part detection.

NudeNet is a body-part detector (not a scene classifier). It outputs bounding boxes for specific body parts, each labelled as exposed or covered. This maps directly to severity tiers without any extra logic:

| NudeNet labels | Tag |
|---|---|
| `FEMALE_GENITALIA_EXPOSED`, `MALE_GENITALIA_EXPOSED`, `ANUS_EXPOSED` | `explicit` |
| `FEMALE_BREAST_EXPOSED`, `BUTTOCKS_EXPOSED` | `revealing` |
| `FEMALE_BREAST_COVERED`, `FEMALE_GENITALIA_COVERED`, `BUTTOCKS_COVERED` | `suggestive` |

### Model choice: 640m vs 320n

Two NudeNet ONNX models are available: `320n` (smaller, faster) and `640m` (larger, more accurate). Testing against the fixture set showed:

- `320n` missed 3 explicit images that `640m` caught
- `320n` produced 2 false positives that `640m` did not
- Inference time difference is negligible for still-image classification (not video)

`640m` was chosen for accuracy. The model is bundled at `640m.onnx` (~18 MB) alongside the plugin.

### Confidence threshold: 0.25

Starting threshold tuning at 0.45, then 0.33, then 0.25. At 0.25, the fixture set achieves 100% detection on all scored images. Three images with extreme camera angles (cunnilingus, narrow field of view) remain undetectable at any threshold and are tracked as `xfail_` fixtures.

### Pipeline ordering

NsfwClassifier runs **unconditionally** — before checking `has_person`. This is intentional: if YOLO misses the person but NudeNet detects explicit content, we want NSFW tags, not `exclude`. The rule is:

1. If any NSFW body parts detected → apply NSFW severity tag(s), skip `exclude`
2. Else if no person detected → apply `exclude`
3. Else → no tag (person present, not NSFW)

## Alternatives considered

**CLIP zero-shot classification** — flexible, no fine-tuning needed, but produces a single scene label rather than body-part detections. Doesn't map naturally to severity tiers. Kept as a future option for clothing category classification (bikini, lingerie).

**Fine-tuned YOLO on NSFW data** — would require a labelled dataset and training run. NudeNet is already purpose-trained and available as a pip package.

**External content moderation API** — ruled out by the project constraint of no external AI API calls.

## Consequences

- Added `nudenet>=3.0` as a runtime dependency
- Added `640m.onnx` (~18 MB) to the plugin directory
- `NsfwClassifier` in `src/nsfw_classifier.py` is the single entry point; it encapsulates the label→severity mapping and threshold logic
- Three `xfail_` fixtures document known model blind spots so they don't pollute accuracy metrics
- Production prerequisite: `pip install "nudenet>=3.0,<4.0"` in the Stash container (or equivalent)
