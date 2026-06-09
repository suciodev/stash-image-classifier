from __future__ import annotations

from pathlib import Path
from nudenet import NudeDetector

# NudeNet v3 body-part label → severity tag.
# Absent entries produce no tag.  Override at construction to remap labels,
# collapse tiers (e.g. all → "nsfw"), or adapt to a future model version.
_DEFAULT_LABEL_MAP: dict[str, str] = {
    # explicit — exposed primary sexual anatomy
    "FEMALE_BREAST_EXPOSED":    "explicit",
    "FEMALE_GENITALIA_EXPOSED": "explicit",
    "MALE_GENITALIA_EXPOSED":   "explicit",
    "ANUS_EXPOSED":             "explicit",
    # revealing — exposed secondary areas
    "BUTTOCKS_EXPOSED":         "revealing",
    "BELLY_EXPOSED":            "revealing",
    # suggestive — covered primary anatomy visible
    "FEMALE_BREAST_COVERED":    "suggestive",
    "FEMALE_GENITALIA_COVERED": "suggestive",
    "BUTTOCKS_COVERED":         "suggestive",
    "ANUS_COVERED":             "suggestive",
    # intentionally unmapped (not NSFW for typical photo libraries):
    # FACE_FEMALE, FACE_MALE, MALE_BREAST_EXPOSED,
    # FEET_EXPOSED, FEET_COVERED, BELLY_COVERED,
    # ARMPITS_EXPOSED, ARMPITS_COVERED
}

_SEVERITY_ORDER = ("explicit", "revealing", "suggestive")


class NsfwClassifier:
    """
    Detects NSFW content using NudeNet (ONNX-based body-part detector).

    Returns a deduplicated list of severity tags in priority order:
    ["explicit", "revealing", "suggestive"].  Empty list means clean.

    label_map is the primary extension point: pass a custom dict to remap
    labels, collapse all tiers to a single tag, or adapt to model changes.

    Known limitations:
      - Accuracy drops for artistic/illustrated content (model trained on photos).
      - Partial bodies in unusual orientations (swimmers, extreme crops) may be missed.
      - min_confidence of 0.45 is intentionally permissive; tune down with fixtures
        if false positives are seen on swimwear or sports content.
    """

    def __init__(
        self,
        min_confidence: float = 0.45,
        label_map: dict[str, str] | None = None,
    ):
        self.detector = NudeDetector()
        self.min_confidence = min_confidence
        self.label_map = label_map if label_map is not None else dict(_DEFAULT_LABEL_MAP)

    def classify(self, image_path: str) -> list[str]:
        """
        Run NSFW classification on a single image.

        Returns tag names in severity order (explicit first).
        Returns [] if the image is safe, not found, or inference fails.
        """
        if not Path(image_path).exists():
            return []
        try:
            detections = self.detector.detect(image_path)
        except Exception:
            return []

        tags: set[str] = set()
        for det in detections:
            if det.get("score", 0.0) < self.min_confidence:
                continue
            tag = self.label_map.get(det.get("class", ""))
            if tag:
                tags.add(tag)

        # Known severity tiers in priority order, then any custom-mapped tags.
        ordered = [t for t in _SEVERITY_ORDER if t in tags]
        custom = sorted(t for t in tags if t not in _SEVERITY_ORDER)
        return ordered + custom
