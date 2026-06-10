"""Integration tests for the _classify_image decision tree in main.py.

Uses lightweight mocks for all three classifiers to verify the branching logic
independently of model accuracy.
"""
from unittest.mock import MagicMock
from main import _classify_image


def _classifiers(has_person=False, nsfw_tags=None, clothing_tags=None):
    person_clf = MagicMock()
    person_clf.has_person.return_value = has_person

    nsfw_clf = MagicMock()
    nsfw_clf.classify.return_value = nsfw_tags or []

    clothing_clf = MagicMock()
    clothing_clf.classify.return_value = clothing_tags or []

    return person_clf, nsfw_clf, clothing_clf


def test_no_person_no_nsfw_returns_exclude():
    p, n, c = _classifiers(has_person=False, nsfw_tags=[])
    assert _classify_image("x.jpg", p, n, c, "exclude") == ["exclude"]
    c.classify.assert_not_called()


def test_no_person_with_nsfw_returns_nsfw_only():
    p, n, c = _classifiers(has_person=False, nsfw_tags=["explicit"])
    result = _classify_image("x.jpg", p, n, c, "exclude")
    assert result == ["explicit"]
    c.classify.assert_not_called()


def test_person_no_nsfw_no_clothing_returns_empty():
    p, n, c = _classifiers(has_person=True, nsfw_tags=[], clothing_tags=[])
    assert _classify_image("x.jpg", p, n, c, "exclude") == []


def test_person_with_clothing_returns_clothing():
    p, n, c = _classifiers(has_person=True, nsfw_tags=[], clothing_tags=["bikini"])
    assert _classify_image("x.jpg", p, n, c, "exclude") == ["bikini"]


def test_person_with_nsfw_and_clothing_returns_both():
    p, n, c = _classifiers(has_person=True, nsfw_tags=["suggestive"], clothing_tags=["lingerie"])
    result = _classify_image("x.jpg", p, n, c, "exclude")
    assert result == ["suggestive", "lingerie"]


def test_person_with_nsfw_no_clothing_returns_nsfw_only():
    p, n, c = _classifiers(has_person=True, nsfw_tags=["revealing"], clothing_tags=[])
    assert _classify_image("x.jpg", p, n, c, "exclude") == ["revealing"]


def test_custom_exclude_tag_name():
    p, n, c = _classifiers(has_person=False, nsfw_tags=[])
    assert _classify_image("x.jpg", p, n, c, "no-subject") == ["no-subject"]
