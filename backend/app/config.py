from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    embedder: str
    clip_model: str
    clip_pretrained: str
    embedding_dimension: int
    cors_origins: tuple[str, ...]

    @property
    def database_path(self) -> Path:
        return self.data_dir / "recalllens.sqlite3"

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"


def _split_origins(value: str) -> tuple[str, ...]:
    return tuple(origin.strip() for origin in value.split(",") if origin.strip())


def get_settings() -> Settings:
    return Settings(
        data_dir=Path(os.getenv("RECALLLENS_DATA_DIR", "data")).resolve(),
        embedder=os.getenv("RECALLLENS_EMBEDDER", "clip").strip().lower(),
        clip_model=os.getenv("RECALLLENS_CLIP_MODEL", "ViT-B-32"),
        clip_pretrained=os.getenv("RECALLLENS_CLIP_PRETRAINED", "laion2b_s34b_b79k"),
        embedding_dimension=int(os.getenv("RECALLLENS_EMBEDDING_DIMENSION", "512")),
        cors_origins=_split_origins(
            os.getenv(
                "RECALLLENS_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,null",
            )
        ),
    )
