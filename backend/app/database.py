from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import ImageRecord, QueryRecord


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def init(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS images (
                    id TEXT PRIMARY KEY,
                    image_path TEXT NOT NULL,
                    thumbnail_path TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    upload_time TEXT NOT NULL,
                    captured_at TEXT,
                    latitude REAL,
                    longitude REAL,
                    location_label TEXT,
                    description TEXT,
                    user_notes TEXT,
                    embedding_id TEXT,
                    index_status TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_images_upload_time ON images(upload_time)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_images_captured_at ON images(captured_at)"
            )
            self._ensure_column(connection, "images", "embedding_model", "TEXT")
            self._ensure_column(connection, "images", "embedding_dimension", "INTEGER")
            self._ensure_column(connection, "images", "embedding_norm", "REAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS queries (
                    id TEXT PRIMARY KEY,
                    query_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    query_embedding_json TEXT NOT NULL,
                    result_ids_json TEXT NOT NULL,
                    captured_from TEXT,
                    captured_to TEXT,
                    location_text TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_queries_created_at ON queries(created_at)"
            )

    def insert_image(self, record: ImageRecord) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO images (
                    id, image_path, thumbnail_path, original_filename, upload_time,
                    captured_at, latitude, longitude, location_label, description,
                    user_notes, embedding_id, index_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.image_path,
                    record.thumbnail_path,
                    record.original_filename,
                    record.upload_time,
                    record.captured_at,
                    record.latitude,
                    record.longitude,
                    record.location_label,
                    record.description,
                    record.user_notes,
                    record.embedding_id,
                    record.index_status,
                ),
            )

    def update_index_status(
        self,
        image_id: str,
        *,
        embedding_id: str | None,
        index_status: str,
        description: str | None,
        embedding_model: str | None = None,
        embedding_dimension: int | None = None,
        embedding_norm: float | None = None,
    ) -> ImageRecord | None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE images
                SET embedding_id = ?,
                    index_status = ?,
                    description = ?,
                    embedding_model = ?,
                    embedding_dimension = ?,
                    embedding_norm = ?
                WHERE id = ?
                """,
                (
                    embedding_id,
                    index_status,
                    description,
                    embedding_model,
                    embedding_dimension,
                    embedding_norm,
                    image_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM images WHERE id = ?",
                (image_id,),
            ).fetchone()
        return ImageRecord.from_row(row) if row else None

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def get_image(self, image_id: str) -> ImageRecord | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM images WHERE id = ?",
                (image_id,),
            ).fetchone()
        return ImageRecord.from_row(row) if row else None

    def list_images(self) -> list[ImageRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM images ORDER BY COALESCE(captured_at, upload_time) DESC"
            ).fetchall()
        return [ImageRecord.from_row(row) for row in rows]

    def get_images_by_ids(self, image_ids: Iterable[str]) -> dict[str, ImageRecord]:
        ids = list(dict.fromkeys(image_ids))
        if not ids:
            return {}

        placeholders = ",".join("?" for _ in ids)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM images WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
        return {row["id"]: ImageRecord.from_row(row) for row in rows}

    def insert_query(self, record: QueryRecord) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO queries (
                    id, query_text, created_at, query_embedding_json, result_ids_json,
                    captured_from, captured_to, location_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.query_text,
                    record.created_at,
                    json.dumps(record.query_embedding, separators=(",", ":")),
                    json.dumps(record.result_ids, separators=(",", ":")),
                    record.captured_from,
                    record.captured_to,
                    record.location_text,
                ),
            )

    def list_queries(self, limit: int = 50) -> list[QueryRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM queries
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [QueryRecord.from_row(row) for row in rows]
