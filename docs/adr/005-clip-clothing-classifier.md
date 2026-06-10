# ADR-005: CLIP Zero-Shot Clothing Classifier

**Status:** Accepted  
**Date:** 2026-06-09

## Context

The plugin needed a way to tag images by clothing category (bikini, swimwear, lingerie, sportswear, dress) without requiring a labelled training dataset or a fixed-label detection model. The existing pipeline already handles person detection (YOLOv8n) and NSFW body-part detection (NudeNet 640m); clothing classification adds a third, orthogonal signal.

## Decision

Use CLIP zero-shot image-text similarity (`openai/clip-vit-base-patch32`) via the HuggingFace `transformers` library.

Clothing classification is gated on person presence (`has_person=True`) — no point tagging clothing when no person is in the frame. NSFW and clothing tags are not mutually exclusive: a lingerie image that also triggers NudeNet receives both tag types.

The model downloads on first use (~600 MB) into the HuggingFace cache (`~/.cache/huggingface/`). No bundled model file.

Labels and tags:

| CLIP prompt | Tag |
|-------------|-----|
| "a person wearing a bikini or two-piece swimwear" | `bikini` |
| "a person wearing a one-piece swimsuit" | `swimwear` |
| "a person wearing lingerie or underwear" | `lingerie` |
| "a person wearing athletic wear, gym clothes, leggings, or a sports bra" | `sportswear` |
| "a person wearing a dress or skirt" | `dress` |
| "a person in regular clothes or other clothing" | *(none — catch-all)* |

Default confidence threshold: 0.5. Tune downward using `tests/check_fixtures.py` if desired categories are missed; raise it if false positives appear.

## Consequences

- `transformers>=4.30.0` added as a dependency. `torch` and `Pillow` were already present.
- First run of the plugin after deploy will trigger a ~600 MB download. Subsequent runs use the cache.
- For fully-offline deployments, pre-download: `python -c "from transformers import CLIPModel, CLIPProcessor; CLIPModel.from_pretrained('openai/clip-vit-base-patch32'); CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')"` once before disconnecting.
- CLIP vit-b32 runs CPU-only; inference adds ~0.3–0.8 s per image on a modern CPU.

## Alternatives considered

**Fashion YOLO (DeepFashion2 checkpoint)** — fixed label set, more accurate per-category, but requires locating/maintaining a checkpoint and retraining to add new labels. CLIP's zero-shot flexibility won here: new clothing categories are just new prompt strings. Revisit if CLIP accuracy on swimwear/nude disambiguation proves insufficient in pool-scene images.

**NudeNet label overlap** — NudeNet already detects `FEMALE_BREAST_COVERED`, `BUTTOCKS_COVERED`, etc., which partially overlaps with "revealing" clothing detection. However NudeNet maps to NSFW severity (body-part exposure), not clothing category (what the person is wearing). The two signals are complementary.
