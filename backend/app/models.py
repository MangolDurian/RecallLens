from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ImageRecord:
    id: str
    image_path: str
    thumbnail_path: str
    original_filename: str
    upload_time: str
    captured_at: str | None
    latitude: float | None
    longitude: float | None
    location_label: str | None
    description: str | None
    user_notes: str | None
    embedding_id: str | None
    index_status: str
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    embedding_norm: float | None = None

    @classmethod
    def from_row(cls, row: Any) -> "ImageRecord":
        return cls(
            id=row["id"],
            image_path=row["image_path"],
            thumbnail_path=row["thumbnail_path"],
            original_filename=row["original_filename"],
            upload_time=row["upload_time"],
            captured_at=row["captured_at"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            location_label=row["location_label"],
            description=row["description"],
            user_notes=row["user_notes"],
            embedding_id=row["embedding_id"],
            index_status=row["index_status"],
            embedding_model=row["embedding_model"],
            embedding_dimension=row["embedding_dimension"],
            embedding_norm=row["embedding_norm"],
        )


@dataclass(frozen=True)
class QueryRecord:
    id: str
    query_text: str
    created_at: str
    query_embedding: list[float]
    result_ids: list[str]
    captured_from: str | None
    captured_to: str | None
    location_text: str | None

    @classmethod
    def from_row(cls, row: Any) -> "QueryRecord":
        return cls(
            id=row["id"],
            query_text=row["query_text"],
            created_at=row["created_at"],
            query_embedding=json.loads(row["query_embedding_json"]),
            result_ids=json.loads(row["result_ids_json"]),
            captured_from=row["captured_from"],
            captured_to=row["captured_to"],
            location_text=row["location_text"],
        )
