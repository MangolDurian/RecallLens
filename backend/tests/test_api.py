from __future__ import annotations

import base64
from datetime import date
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.service import _infer_date_range_from_query


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        embedder="hash",
        clip_model="ViT-B-32",
        clip_pretrained="test",
        embedding_dimension=512,
        cors_origins=("http://localhost:5173",),
    )
    return TestClient(create_app(settings))


def image_bytes(color: tuple[int, int, int]) -> BytesIO:
    image = Image.new("RGB", (80, 80), color)
    buffer = BytesIO()
    image.save(buffer, "JPEG")
    buffer.seek(0)
    return buffer


def exif_image_bytes(color: tuple[int, int, int]) -> BytesIO:
    image = Image.new("RGB", (80, 80), color)
    exif = Image.Exif()
    exif[36867] = "2026:06:01 08:15:00"
    exif[34853] = {
        1: "N",
        2: (22.0, 54.0, 54.0),
        3: "E",
        4: (113.0, 50.0, 96.0),
    }
    buffer = BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    buffer.seek(0)
    return buffer


def upload_image(
    client: TestClient,
    *,
    filename: str,
    color: tuple[int, int, int],
    note: str = "",
    location: str = "",
) -> dict:
    response = client.post(
        "/api/images",
        files={"image": (filename, image_bytes(color), "image/jpeg")},
        data={
            "note": note,
            "capturedAt": "2026-06-02T09:30",
            "latitude": "22.915",
            "longitude": "113.836",
            "locationLabel": location,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_creates_files_record_and_index(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    record = upload_image(
        client,
        filename="keys.jpg",
        color=(240, 20, 20),
        note="Keys near the entry shelf",
        location="Entry shelf",
    )

    assert record["indexStatus"] == "indexed"
    assert record["embeddingId"] == record["id"]
    assert record["embeddingModel"] == "hash"
    assert record["embeddingDimension"] == 512
    assert record["embeddingNorm"] == 1.0
    assert record["description"].startswith("Semantic tags:")
    assert record["userNotes"] == "Keys near the entry shelf"
    assert record["location"]["label"] == "Entry shelf"
    assert (tmp_path / "images").exists()
    assert (tmp_path / "thumbnails").exists()
    assert (tmp_path / "index" / "ids.json").exists()

    list_response = client.get("/api/images")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == record["id"]

    tags_response = client.get("/api/tags")
    assert tags_response.status_code == 200
    assert any(record["id"] in item["imageIds"] for item in tags_response.json())


def test_upload_uses_exif_metadata_when_form_fields_are_missing(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post(
        "/api/images",
        files={"image": ("exif-backpack.jpg", exif_image_bytes((30, 60, 235)), "image/jpeg")},
        data={"note": "Backpack photo with camera metadata"},
    )

    assert response.status_code == 201, response.text
    record = response.json()
    assert record["capturedAt"] == "2026-06-01T08:15:00"
    assert record["location"]["latitude"] == 22.915
    assert round(record["location"]["longitude"], 4) == 113.86


def test_json_base64_upload_works_without_multipart_body(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    image_payload = base64.b64encode(image_bytes((30, 60, 235)).getvalue()).decode("ascii")

    response = client.post(
        "/api/images",
        json={
            "imageBase64": image_payload,
            "originalFilename": "blue-backpack.jpg",
            "note": "Blue backpack under the office desk",
            "locationLabel": "Office desk",
        },
    )

    assert response.status_code == 201, response.text
    record = response.json()
    assert record["indexStatus"] == "indexed"
    assert record["originalFilename"] == "blue-backpack.jpg"


def test_static_fallback_serves_pwa_shell(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    app_shell = client.get("/app/")
    assert app_shell.status_code == 200
    assert "./manifest.webmanifest" in app_shell.text

    manifest = client.get("/app/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.json()["start_url"] == "./"

    service_worker = client.get("/app/sw.js")
    assert service_worker.status_code == 200
    assert "recalllens-static-shell" in service_worker.text

    icon = client.get("/app/icon.svg")
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/svg")


def test_search_returns_semantically_closest_image_first(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    red = upload_image(
        client,
        filename="keys.jpg",
        color=(245, 30, 25),
        note="Keys on the red tray",
        location="Hallway",
    )
    blue = upload_image(
        client,
        filename="backpack.jpg",
        color=(30, 60, 235),
        note="Blue backpack under desk",
        location="Office",
    )

    response = client.post(
        "/api/search",
        json={"queryText": "blue backpack", "limit": 2},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["imageId"] for item in results] == [blue["id"], red["id"]]
    assert results[0]["score"] > results[1]["score"]

    queries = client.get("/api/queries")
    assert queries.status_code == 200
    query_record = queries.json()[0]
    assert query_record["queryText"] == "blue backpack"
    assert query_record["results"] == [blue["id"], red["id"]]
    assert len(query_record["queryEmbedding"]) == 512


def test_search_uses_notes_and_location_as_ranking_signals(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    upload_image(
        client,
        filename="blue-backpack.jpg",
        color=(30, 60, 235),
        note="Blue backpack under desk",
        location="Office",
    )
    passport = upload_image(
        client,
        filename="green-box.jpg",
        color=(30, 180, 60),
        note="Passport inside the travel drawer",
        location="Bedroom drawer",
    )

    response = client.post(
        "/api/search",
        json={"queryText": "passport drawer", "limit": 1},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["imageId"] == passport["id"]


def test_index_persists_across_app_restarts(tmp_path: Path) -> None:
    first_client = make_client(tmp_path)
    record = upload_image(
        first_client,
        filename="blue-cup.jpg",
        color=(20, 70, 240),
        note="Blue cup on kitchen counter",
        location="Kitchen",
    )

    restarted_client = make_client(tmp_path)
    response = restarted_client.post(
        "/api/search",
        json={"queryText": "blue cup", "limit": 1},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["imageId"] == record["id"]


def test_empty_library_search_returns_empty_results(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    response = client.post("/api/search", json={"queryText": "keys", "limit": 5})

    assert response.status_code == 200
    assert response.json()["results"] == []


def test_search_date_range_inference_from_natural_language() -> None:
    start, end = _infer_date_range_from_query(
        "我上周拍的钥匙照片在哪里？",
        today=date(2026, 6, 4),
    )
    assert start.isoformat() == "2026-05-25T00:00:00"
    assert end.isoformat() == "2026-05-31T23:59:59.999999"

    start, end = _infer_date_range_from_query(
        "blue backpack from the last 7 days",
        today=date(2026, 6, 4),
    )
    assert start.isoformat() == "2026-05-29T00:00:00"
    assert end.isoformat() == "2026-06-04T23:59:59.999999"


def test_bad_image_and_empty_query_return_clear_errors(tmp_path: Path) -> None:
    client = make_client(tmp_path)

    bad_upload = client.post(
        "/api/images",
        files={"image": ("broken.jpg", BytesIO(b"not an image"), "image/jpeg")},
    )
    assert bad_upload.status_code == 400
    assert "readable image" in bad_upload.json()["detail"]

    empty_query = client.post("/api/search", json={"queryText": "   ", "limit": 5})
    assert empty_query.status_code == 400
    assert "empty" in empty_query.json()["detail"]
