from __future__ import annotations

from pathlib import Path
from PIL import Image

from transformers import CLIPModel, CLIPProcessor
import torch

_MODEL_ID = "openai/clip-vit-base-patch32"

# Each entry: (CLIP prompt, tag name or None for catch-all)
_LABEL_MAP: list[tuple[str, str | None]] = [
    ("a person wearing a bikini or two-piece swimwear", "bikini"),
    ("a person wearing a one-piece swimsuit, one-piece bathing suit, or maillot", "swimwear"),
    ("a person wearing lingerie, lace underwear, or a bra and panties set", "lingerie"),
    ("a person exercising or at the gym wearing athletic clothing, sports bra, or gym leggings", "sportswear"),
    ("a person wearing a fashion dress, mini dress, cocktail dress, bodycon dress, skirt, or street style outfit", "dress"),
    ("a person in regular everyday clothes, casual wear, or other clothing", None),  # catch-all, no tag
]

_LABELS = [prompt for prompt, _ in _LABEL_MAP]

# Tag names this classifier can produce. Exposed for validation in main.py.
CLOTHING_TAGS: frozenset[str] = frozenset(tag for _, tag in _LABEL_MAP if tag is not None)


class ClothingClassifier:
    """
    Detects clothing category using CLIP zero-shot image-text similarity.

    Call only when a person is present in the image — classifies clothing worn
    by the subject.  Returns a list of tag names (at most one from the label
    map), or an empty list when confidence is below threshold or no label fits.

    The model (~600 MB) is downloaded from HuggingFace on first use and cached
    in the default HuggingFace cache directory (~/.cache/huggingface/).

    Known limitations:
      - Accuracy drops for illustrated/artistic content (model trained on photos).
      - Partial-body crops may confuse the model (no full clothing visible).
      - min_confidence of 0.4 may produce false positives; raise it if you see wrong tags.
    """

    def __init__(self, min_confidence: float = 0.4, model_id: str = _MODEL_ID):
        self._processor = CLIPProcessor.from_pretrained(model_id)
        self._model = CLIPModel.from_pretrained(model_id)
        self._model.eval()
        self.min_confidence = min_confidence

    def classify(self, image_path: str) -> list[str]:
        """
        Run clothing classification on a single image.

        Returns at most one tag name (highest-probability label above threshold).
        Returns [] if the image is missing, confidence is too low, or inference fails.
        """
        if not Path(image_path).exists():
            return []
        try:
            image = Image.open(image_path).convert("RGB")
            inputs = self._processor(text=_LABELS, images=image, return_tensors="pt", padding=True)
            with torch.no_grad():
                logits = self._model(**inputs).logits_per_image[0]
            probs = logits.softmax(dim=0)
            best_idx = int(probs.argmax())
            if probs[best_idx].item() < self.min_confidence:
                return []
            tag = _LABEL_MAP[best_idx][1]
            return [tag] if tag else []
        except Exception:
            return []
