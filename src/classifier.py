from pathlib import Path
from ultralytics import YOLO

_PERSON_CLASS = 0  # COCO class index for "person"


class ImageClassifier:
    """
    Detects whether a person is present using YOLOv8 nano.
    Model downloads once on first use (~6MB) and is cached locally.
    Pass model_path to use a bundled/offline copy instead.
    """

    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.25):
        self.model = YOLO(model_path)
        self.confidence = confidence

    def has_person(self, image_path: str) -> bool:
        if not Path(image_path).exists():
            return False
        results = self.model(
            image_path,
            classes=[_PERSON_CLASS],
            conf=self.confidence,
            verbose=False,
        )
        return len(results[0].boxes) > 0
