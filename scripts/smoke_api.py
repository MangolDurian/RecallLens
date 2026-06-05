from __future__ import annotations

import base64
import tempfile
import sys
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import Settings
from backend.app.main import create_app


def make_image_payload(color: tuple[int, int, int]) -> str:
    buffer = BytesIO()
    Image.new("RGB", (96, 96), color).save(buffer, "JPEG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def main() -> None:
    settings = Settings(
        data_dir=Path(tempfile.mkdtemp(prefix="recalllens-api-smoke-")),
        embedder="hash",
        clip_model="ViT-B-32",
        clip_pretrained="smoke",
        embedding_dimension=512,
        cors_origins=("http://localhost:5173", "null"),
    )
    client = TestClient(create_app(settings))

    root = client.get("/", follow_redirects=False)
    assert root.status_code in {307, 308}
    assert root.headers["location"] == "/app/"

    static_app = client.get("/app/")
    assert static_app.status_code == 200
    assert "RecallLens" in static_app.text
    assert "./manifest.webmanifest" in static_app.text

    manifest = client.get("/app/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.json()["name"] == "RecallLens"

    static_sw = client.get("/app/sw.js")
    assert static_sw.status_code == 200
    assert "recalllens-static-shell" in static_sw.text

    static_icon = client.get("/app/icon.svg")
    assert static_icon.status_code == 200
    assert "image/svg" in static_icon.headers["content-type"]

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["indexedImages"] == 0

    upload = client.post(
        "/api/images",
        json={
            "imageBase64": make_image_payload((20, 60, 245)),
            "originalFilename": "blue-backpack.jpg",
            "note": "Blue backpack under the office desk",
            "capturedAt": "2026-06-03T20:00",
            "locationLabel": "Office desk",
        },
    )
    assert upload.status_code == 201, upload.text
    record = upload.json()
    assert record["indexStatus"] == "indexed"
    assert record["description"].startswith("Semantic tags:")
    assert record["embeddingModel"] == "hash"
    assert record["embeddingDimension"] == 512
    assert record["embeddingNorm"] == 1.0

    detail = client.get(f"/api/images/{record['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == record["id"]

    library = client.get("/api/images")
    assert library.status_code == 200
    assert library.json()[0]["id"] == record["id"]

    tags = client.get("/api/tags")
    assert tags.status_code == 200
    tag_map = {item["tag"]: item for item in tags.json()}
    assert "backpack" in tag_map
    assert record["id"] in tag_map["backpack"]["imageIds"]

    thumbnail = client.get(record["thumbnailUrl"])
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"].startswith("image/")

    search = client.post(
        "/api/search",
        json={"queryText": "blue backpack office", "limit": 1},
    )
    assert search.status_code == 200, search.text
    results = search.json()["results"]
    assert results and results[0]["imageId"] == record["id"]
    assert results[0]["embeddingDimension"] == 512

    queries = client.get("/api/queries")
    assert queries.status_code == 200
    query_history = queries.json()
    assert query_history[0]["queryText"] == "blue backpack office"
    assert query_history[0]["results"] == [record["id"]]
    assert len(query_history[0]["queryEmbedding"]) == 512

    print("RecallLens API smoke test passed.")
    print(f"Data dir: {settings.data_dir}")


if __name__ == "__main__":
    main()
