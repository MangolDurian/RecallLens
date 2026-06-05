from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import Settings
from backend.app.database import Database
from backend.app.embeddings import HashEmbeddingService
from backend.app.service import RecallLensService
from backend.app.storage import ImageStorage
from backend.app.vector_index import VectorIndex


@dataclass(frozen=True)
class DemoItem:
    filename: str
    label: str
    color: tuple[int, int, int]
    note: str
    location: str
    captured_days_ago: int


class MemoryUpload:
    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self._data = data

    async def read(self) -> bytes:
        return self._data


DEMO_ITEMS = (
    DemoItem("keys-entry-tray.jpg", "KEYS", (230, 44, 35), "Keys on the red entry tray", "Entry shelf", 10),
    DemoItem("blue-backpack-office.jpg", "BACKPACK", (25, 82, 230), "Blue backpack under the office desk", "Office desk", 1),
    DemoItem("passport-drawer.jpg", "PASSPORT", (35, 150, 82), "Passport inside the travel drawer", "Bedroom drawer", 2),
    DemoItem("charger-nightstand.jpg", "CHARGER", (245, 245, 238), "Phone charger beside the nightstand lamp", "Bedroom nightstand", 3),
    DemoItem("thermos-kitchen.jpg", "THERMOS", (32, 120, 190), "Blue thermos cup on the kitchen counter", "Kitchen counter", 4),
    DemoItem("wallet-shelf.jpg", "WALLET", (45, 45, 45), "Black wallet on the hallway shelf", "Hallway shelf", 5),
    DemoItem("phone-sofa.jpg", "PHONE", (28, 28, 32), "Phone between the sofa cushions", "Living room sofa", 0),
    DemoItem("laptop-office.jpg", "LAPTOP", (120, 122, 130), "Laptop on the office desk", "Office desk", 6),
    DemoItem("glasses-book.jpg", "GLASSES", (238, 238, 238), "Glasses on top of the notebook", "Reading table", 2),
    DemoItem("remote-cabinet.jpg", "REMOTE", (78, 78, 84), "Remote control in the media cabinet", "Living room cabinet", 1),
)


def make_service(data_dir: Path) -> RecallLensService:
    embeddings = HashEmbeddingService()
    settings = Settings(
        data_dir=data_dir.resolve(),
        embedder="hash",
        clip_model="ViT-B-32",
        clip_pretrained="demo",
        embedding_dimension=embeddings.dimension,
        cors_origins=("http://localhost:5173", "null"),
    )
    return RecallLensService(
        settings=settings,
        database=Database(settings.database_path),
        storage=ImageStorage(settings.images_dir, settings.thumbnails_dir),
        embeddings=embeddings,
        vector_index=VectorIndex(settings.index_dir, embeddings.dimension),
    )


def make_demo_image(item: DemoItem) -> bytes:
    image = Image.new("RGB", (900, 620), item.color)
    draw = ImageDraw.Draw(image)
    text_color = (255, 255, 255) if sum(item.color) < 420 else (34, 42, 39)
    draw.rectangle((42, 42, 858, 578), outline=text_color, width=8)
    draw.text((82, 190), item.label, fill=text_color)
    draw.text((82, 260), item.location, fill=text_color)
    draw.text((82, 326), item.note, fill=text_color)
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


async def seed_demo(data_dir: Path, *, reset: bool) -> None:
    data_dir = data_dir.resolve()
    if reset and data_dir.exists():
        _ensure_reset_path_is_safe(data_dir)
        shutil.rmtree(data_dir)

    service = make_service(data_dir)
    today = date.today()
    records = []
    created = 0
    existing_by_filename = {
        record.original_filename: record
        for record in service.list_images()
        if record.index_status == "indexed"
    }

    for item in DEMO_ITEMS:
        existing = existing_by_filename.get(item.filename)
        if existing is not None:
            records.append(existing)
            continue

        captured = datetime.combine(
            today - timedelta(days=item.captured_days_ago),
            time(hour=9 + (item.captured_days_ago % 10), minute=15),
        )
        record = await service.add_image(
            MemoryUpload(item.filename, make_demo_image(item)),
            note=item.note,
            captured_at=captured.isoformat(timespec="minutes"),
            latitude=22.915 if "office" in item.location.lower() else None,
            longitude=113.836 if "office" in item.location.lower() else None,
            location_label=item.location,
        )
        records.append(record)
        created += 1

    assert len(records) == len(DEMO_ITEMS)
    assert len(service.list_images()) >= len(DEMO_ITEMS)

    query_expectations = (
        ("blue backpack from the last 7 days", "blue-backpack-office.jpg"),
        ("passport drawer", "passport-drawer.jpg"),
        ("keys entry shelf", "keys-entry-tray.jpg"),
        ("charger nightstand", "charger-nightstand.jpg"),
    )
    for query_text, expected_filename in query_expectations:
        results = service.search(
            query_text=query_text,
            limit=1,
            captured_from=None,
            captured_to=None,
            location_text=None,
        )
        assert results, f"No result for {query_text!r}"
        top_record = results[0][0]
        assert top_record.original_filename == expected_filename, (
            f"Expected {expected_filename}, got {top_record.original_filename}"
        )

    print(f"Demo library ready with {len(records)} photos ({created} new).")
    print(f"Data dir: {data_dir.resolve()}")
    print("Run with: RECALLLENS_EMBEDDER=hash RECALLLENS_DATA_DIR=data/demo uv run uvicorn backend.app.main:app --reload --port 8000")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed RecallLens with local demo object photos.")
    parser.add_argument("--data-dir", default="data/demo", help="Demo data directory.")
    parser.add_argument("--reset", action="store_true", help="Delete the demo data directory before seeding.")
    return parser.parse_args()


def _ensure_reset_path_is_safe(data_dir: Path) -> None:
    allowed_root = (PROJECT_ROOT / "data").resolve()
    if data_dir == allowed_root or allowed_root in data_dir.parents:
        return
    raise SystemExit(f"Refusing to reset outside project data directory: {data_dir}")


def main() -> None:
    args = parse_args()
    asyncio.run(seed_demo(Path(args.data_dir), reset=args.reset))


if __name__ == "__main__":
    main()
