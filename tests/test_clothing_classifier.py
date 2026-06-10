import pytest
import torch
from unittest.mock import MagicMock, patch
from PIL import Image as PILImage

from src.clothing_classifier import ClothingClassifier, _LABEL_MAP, _LABELS


def _make_image(tmp_path, name="test.jpg"):
    path = tmp_path / name
    PILImage.new("RGB", (10, 10), color=(128, 128, 128)).save(str(path))
    return path


def _make_classifier(label_idx=None, min_confidence=0.5):
    """Create a ClothingClassifier with a mocked CLIP model.

    label_idx: index into _LABELS to give high probability; None = uniform (low prob).
    """
    logits = torch.zeros(len(_LABELS))
    if label_idx is not None:
        logits[label_idx] = 10.0  # softmax → ~1.0 at this index

    mock_output = MagicMock()
    mock_output.logits_per_image = logits.unsqueeze(0)

    mock_model = MagicMock()
    mock_model.return_value = mock_output

    mock_processor = MagicMock()
    mock_processor.return_value = {}

    with patch("src.clothing_classifier.CLIPModel") as mock_model_cls, \
         patch("src.clothing_classifier.CLIPProcessor") as mock_proc_cls:
        mock_model_cls.from_pretrained.return_value = mock_model
        mock_proc_cls.from_pretrained.return_value = mock_processor
        clf = ClothingClassifier(min_confidence=min_confidence)

    clf._model = mock_model
    clf._processor = mock_processor
    return clf


def test_returns_empty_for_missing_file():
    clf = _make_classifier()
    assert clf.classify("/nonexistent/image.jpg") == []


def test_returns_empty_when_confidence_below_threshold(tmp_path):
    img = _make_image(tmp_path)
    # Uniform logits → all probs ~equal and well below 0.5 threshold
    clf = _make_classifier(label_idx=None, min_confidence=0.5)
    assert clf.classify(str(img)) == []


@pytest.mark.parametrize("tag", ["bikini", "swimwear", "lingerie", "sportswear", "dress"])
def test_returns_clothing_tag(tmp_path, tag):
    img = _make_image(tmp_path)
    idx = next(i for i, (_, t) in enumerate(_LABEL_MAP) if t == tag)
    clf = _make_classifier(label_idx=idx)
    assert clf.classify(str(img)) == [tag]


def test_catchall_label_returns_empty(tmp_path):
    img = _make_image(tmp_path)
    idx = next(i for i, (_, tag) in enumerate(_LABEL_MAP) if tag is None)
    clf = _make_classifier(label_idx=idx)
    assert clf.classify(str(img)) == []


def test_returns_empty_on_model_exception(tmp_path):
    img = _make_image(tmp_path)
    clf = _make_classifier()
    clf._model.side_effect = RuntimeError("CLIP error")
    assert clf.classify(str(img)) == []
