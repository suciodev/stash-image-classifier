from pathlib import Path
from ultralytics import YOLO

_PERSON_CLASS = 0  # COCO class index for "person"
_DEFAULT_MODEL = str(Path(__file__).parent.parent / "yolov8n.pt")


class ImageClassifier:
    """
    Detects whether a person is the subject of an image using YOLOv8s.

    Two thresholds filter incidental detections (background figures, partial limbs):
      - min_confidence: passed directly to YOLO; boxes below this are never returned
      - min_area_fraction: post-inference filter; boxes smaller than this fraction
        of image area are ignored (eliminates tiny background figures)

    Known limitations:
      - Horizontal/submerged bodies in water are rarely detected (COCO training bias)
      - Digital illustrations are not detected (model trained on photographs)
    """

    def __init__(
        self,
        model_path: str = _DEFAULT_MODEL,
        min_confidence: float = 0.60,
        min_area_fraction: float = 0.05,
    ):
        self.model = YOLO(model_path)
        self.min_confidence = min_confidence
        self.min_area_fraction = min_area_fraction

    def has_person(self, image_path: str) -> bool:
        if not Path(image_path).exists():
            return False
        results = self.model(
            image_path,
            classes=[_PERSON_CLASS],
            conf=self.min_confidence,
            verbose=False,
        )
        r = results[0]
        img_area = r.orig_shape[0] * r.orig_shape[1]
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            if (x2 - x1) * (y2 - y1) / img_area >= self.min_area_fraction:
                return True
        return False
