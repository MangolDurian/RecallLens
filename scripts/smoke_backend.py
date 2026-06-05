from __future__ import annotations

import asyncio
import tempfile
import sys
from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import Settings
from backend.app.database import Database
from backend.app.embeddings import HashEmbeddingService
from backend.app.service import RecallLensService
from backend.app.storage import ImageStorage
from backend.app.vector_index import VectorIndex


class MemoryUpload:
    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self._data = data

    async def read(self) -> bytes:
        return self._data


def make_image(color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (96, 96), color).save(buffer, "JPEG")
    return buffer.getvalue()


def make_exif_image(color: tuple[int, int, int], captured_at: datetime) -> bytes:
    exif = Image.Exif()
    exif[36867] = captured_at.strftime("%Y:%m:%d %H:%M:%S")
    exif[34853] = {
        1: "N",
        2: (22.0, 54.0, 54.0),
        3: "E",
        4: (113.0, 50.0, 96.0),
    }
    buffer = BytesIO()
    Image.new("RGB", (96, 96), color).save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


def make_service(root: Path) -> RecallLensService:
    settings = Settings(
        data_dir=root,
        embedder="hash",
        clip_model="ViT-B-32",
        clip_pretrained="smoke",
        embedding_dimension=512,
        cors_origins=("http://localhost:5173",),
    )
    embeddings = HashEmbeddingService()
    return RecallLensService(
        settings=settings,
        database=Database(settings.database_path),
        storage=ImageStorage(settings.images_dir, settings.thumbnails_dir),
        embeddings=embeddings,
        vector_index=VectorIndex(settings.index_dir, embeddings.dimension),
    )


async def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="recalllens-smoke-"))
    service = make_service(root)
    today = date.today()
    old_capture = datetime.combine(today - timedelta(days=10), time(hour=9, minute=30))
    recent_capture = datetime.combine(today - timedelta(days=1), time(hour=20))

    red_keys = await service.add_image(
        MemoryUpload("keys.jpg", make_image((245, 30, 25))),
        note="Keys on the red entry tray",
        captured_at=old_capture.isoformat(timespec="minutes"),
        latitude=22.915,
        longitude=113.836,
        location_label="Entry shelf",
    )
    blue_backpack = await service.add_image(
        MemoryUpload("blue-backpack.jpg", make_exif_image((20, 60, 245), recent_capture)),
        note="Blue backpack under the office desk",
        captured_at=None,
        latitude=None,
        longitude=None,
        location_label="Office desk",
    )
    passport = await service.add_image(
        MemoryUpload("green-box.jpg", make_image((30, 180, 60))),
        note="Passport inside the travel drawer",
        captured_at=recent_capture.isoformat(),
        latitude=None,
        longitude=None,
        location_label="Bedroom drawer",
    )

    assert red_keys.index_status == "indexed"
    assert blue_backpack.index_status == "indexed"
    assert passport.index_status == "indexed"
    assert blue_backpack.embedding_model == "hash"
    assert blue_backpack.embedding_dimension == 512
    assert blue_backpack.embedding_norm == 1.0
    assert red_keys.description and red_keys.description.startswith("Semantic tags:")
    assert blue_backpack.description and blue_backpack.description.startswith("Semantic tags:")
    tag_groups = dict(service.list_tag_groups())
    assert "backpack" in tag_groups
    assert blue_backpack.id in tag_groups["backpack"]
    assert blue_backpack.captured_at == recent_capture.isoformat()
    assert blue_backpack.latitude == 22.915
    assert round(blue_backpack.longitude or 0, 4) == 113.86
    assert service.list_images()[0].id == blue_backpack.id

    backpack_results = service.search(
        query_text="blue backpack",
        limit=2,
        captured_from=None,
        captured_to=None,
        location_text=None,
    )
    assert backpack_results[0][0].id == blue_backpack.id

    office_results = service.search(
        query_text="backpack",
        limit=2,
        captured_from=None,
        captured_to=None,
        location_text="office",
    )
    assert [record.id for record, _ in office_results] == [blue_backpack.id]

    passport_results = service.search(
        query_text="passport drawer",
        limit=1,
        captured_from=None,
        captured_to=None,
        location_text=None,
    )
    assert [record.id for record, _ in passport_results] == [passport.id]

    old_key_results = service.search(
        query_text="keys",
        limit=2,
        captured_from=old_capture.date().isoformat(),
        captured_to=old_capture.date().isoformat(),
        location_text=None,
    )
    assert [record.id for record, _ in old_key_results] == [red_keys.id]

    recent_results = service.search(
        query_text="blue backpack from the last 7 days",
        limit=2,
        captured_from=None,
        captured_to=None,
        location_text=None,
    )
    assert [record.id for record, _ in recent_results][0] == blue_backpack.id
    query_history = service.list_queries(limit=5)
    assert query_history[0].query_text == "blue backpack from the last 7 days"
    assert query_history[0].result_ids[0] == blue_backpack.id
    assert len(query_history[0].query_embedding) == 512

    restarted = make_service(root)
    reloaded_results = restarted.search(
        query_text="blue backpack",
        limit=1,
        captured_from=None,
        captured_to=None,
        location_text=None,
    )
    assert reloaded_results[0][0].id == blue_backpack.id
    assert restarted.list_queries(limit=10)

    print("RecallLens backend smoke test passed.")
    print(f"Data dir: {root}")


if __name__ == "__main__":
    asyncio.run(main())
