from unittest.mock import MagicMock
from main import run_classify


def _make_client(images_by_call, count=1):
    client = MagicMock()
    _counter = [0]
    _tag_map = {}

    def find_or_create(name):
        if name not in _tag_map:
            _counter[0] += 1
            _tag_map[name] = f"tid-{_counter[0]}"
        return _tag_map[name]

    client.find_or_create_tag.side_effect = find_or_create
    client._tag_map = _tag_map
    client.count_images_by_tag.return_value = count
    client.find_images_by_tag.side_effect = images_by_call
    return client


def _make_classifiers(has_person=False, nsfw_tags=None):
    clf = MagicMock()
    clf.has_person.return_value = has_person
    nsfw = MagicMock()
    nsfw.classify.return_value = nsfw_tags or []
    return clf, nsfw


def test_classify_marked_images_applies_classifier_tag_and_swaps_marker():
    """Image with no person gets 'exclude' added; marker swapped pending→done in one call."""
    client = _make_client(
        images_by_call=[
            [{"id": "img-1", "path": "/data/no_person.jpg", "tag_ids": []}],
            [],
        ],
        count=1,
    )
    clf, nsfw = _make_classifiers(has_person=False)

    run_classify(client, clf, nsfw, {"tagged_only": "true"})

    tag_map = client._tag_map
    client.update_image_tags.assert_called_once()
    image_id, add_ids, remove_ids, _ = client.update_image_tags.call_args[0]
    assert image_id == "img-1"
    assert tag_map["exclude"] in add_ids
    assert tag_map["percepttag:done"] in add_ids
    assert tag_map["percepttag:pending"] in remove_ids


def test_classify_marked_images_swaps_marker_when_no_classifier_tags_change():
    """Image with person detected gets no classifier tag; marker still swapped pending→done."""
    client = _make_client(
        images_by_call=[
            [{"id": "img-1", "path": "/data/person.jpg", "tag_ids": []}],
            [],
        ],
        count=1,
    )
    clf, nsfw = _make_classifiers(has_person=True)

    run_classify(client, clf, nsfw, {"tagged_only": "true"})

    tag_map = client._tag_map
    client.update_image_tags.assert_called_once()
    image_id, add_ids, remove_ids, _ = client.update_image_tags.call_args[0]
    assert image_id == "img-1"
    assert tag_map["percepttag:done"] in add_ids
    assert tag_map["percepttag:pending"] in remove_ids
    assert tag_map.get("exclude") not in add_ids
