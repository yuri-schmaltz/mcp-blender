import base64
import json
from unittest.mock import MagicMock

import pytest

from blender_mcp import server


@pytest.mark.parametrize(
    "bbox, expected",
    [
        (None, None),
        ([1, 2, 3], [1, 2, 3]),
        ([1.0, 2.0, 3.0], [33, 66, 100]),
    ],
)
def test_process_bbox(bbox, expected):
    assert server._process_bbox(bbox) == expected


def test_process_bbox_rejects_non_positive_values():
    with pytest.raises(ValueError):
        server._process_bbox([0, 1, 2])


def test_generate_hyper3d_model_via_text_formats_command(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.send_command.return_value = {
        "submit_time": "now",
        "uuid": "task-123",
        "jobs": {"subscription_key": "sub-key"},
    }
    monkeypatch.setattr(server, "get_blender_connection", lambda: mock_conn)

    response = server.generate_hyper3d_model_via_text(
        None, text_prompt="a cube", bbox_condition=[1.0, 2.0, 3.0]
    )

    payload = mock_conn.send_command.call_args[0][1]
    assert payload["text_prompt"] == "a cube"
    assert payload["images"] is None
    assert payload["bbox_condition"] == [33, 66, 100]

    parsed_response = json.loads(response)
    assert parsed_response["task_uuid"] == "task-123"
    assert parsed_response["subscription_key"] == "sub-key"


def test_generate_hyper3d_model_via_images_with_invalid_path(monkeypatch):
    monkeypatch.setattr(
        server, "get_blender_connection", lambda: pytest.fail("Should not connect")
    )

    response = server.generate_hyper3d_model_via_images(
        None, input_image_paths=["/does/not/exist.png"]
    )

    assert response == "Error: not all image paths are valid!"


def test_generate_hyper3d_model_via_images_with_invalid_url(monkeypatch):
    monkeypatch.setattr(
        server, "get_blender_connection", lambda: pytest.fail("Should not connect")
    )

    response = server.generate_hyper3d_model_via_images(
        None, input_image_urls=["not-a-url"]
    )

    assert response == "Error: not all image URLs are valid!"


def test_generate_hyper3d_model_via_images_uses_urls(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.send_command.return_value = {
        "submit_time": True,
        "uuid": "url-task",
        "jobs": {"subscription_key": "url-sub"},
    }
    monkeypatch.setattr(server, "get_blender_connection", lambda: mock_conn)

    response = server.generate_hyper3d_model_via_images(
        None,
        input_image_urls=["https://example.com/image.png"],
        bbox_condition=[1, 1, 1],
    )

    payload = mock_conn.send_command.call_args[0][1]
    assert payload["images"] == ["https://example.com/image.png"]
    assert payload["bbox_condition"] == [1, 1, 1]

    parsed = json.loads(response)
    assert parsed["task_uuid"] == "url-task"
    assert parsed["subscription_key"] == "url-sub"


def test_generate_hyper3d_model_via_images_reads_files(monkeypatch, tmp_path):
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"fake-bytes")

    mock_conn = MagicMock()
    mock_conn.send_command.return_value = {
        "submit_time": True,
        "uuid": "file-task",
        "jobs": {"subscription_key": "file-sub"},
    }
    monkeypatch.setattr(server, "get_blender_connection", lambda: mock_conn)

    response = server.generate_hyper3d_model_via_images(
        None, input_image_paths=[str(image_path)]
    )

    payload = mock_conn.send_command.call_args[0][1]
    assert len(payload["images"]) == 1
    suffix, encoded = payload["images"][0]
    assert suffix == ".png"
    assert base64.b64decode(encoded) == b"fake-bytes"

    parsed = json.loads(response)
    assert parsed["task_uuid"] == "file-task"
    assert parsed["subscription_key"] == "file-sub"
