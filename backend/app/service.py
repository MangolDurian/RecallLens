from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from .analysis import SemanticLabeler
from .config import Settings
from .database import Database
from .embeddings import EmbeddingError, EmbeddingService
from .models import ImageRecord, QueryRecord
from .storage import ImageStorage, InvalidImageError
from .vector_index import VectorIndex


class ImageNotFoundError(LookupError):
    pass


class RecallLensService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        storage: ImageStorage,
        embeddings: EmbeddingService,
        vector_index: VectorIndex,
    ) -> None:
        self.settings = settings
        self.database = database
        self.storage = storage
        self.embeddings = embeddings
        self.vector_index = vector_index
        self.labeler = SemanticLabeler(embeddings)
        self.database.init()

    async def add_image(
        self,
        upload: UploadFile,
        *,
        note: str | None,
        captured_at: str | None,
        latitude: float | None,
        longitude: float | None,
        location_label: str | None,
    ) -> ImageRecord:
        stored = await self.storage.save_upload(upload)
        upload_time = datetime.now(timezone.utc).isoformat()
        image_path = self._relative_to_data(stored.image_path)
        thumbnail_path = self._relative_to_data(stored.thumbnail_path)
        captured_at_value = _clean_text(captured_at) or stored.metadata.captured_at
        latitude_value = latitude if latitude is not None else stored.metadata.latitude
        longitude_value = longitude if longitude is not None else stored.metadata.longitude

        record = ImageRecord(
            id=stored.id,
            image_path=image_path,
            thumbnail_path=thumbnail_path,
            original_filename=stored.original_filename,
            upload_time=upload_time,
            captured_at=captured_at_value,
            latitude=latitude_value,
            longitude=longitude_value,
            location_label=_clean_text(location_label),
            description=None,
            user_notes=_clean_text(note),
            embedding_id=None,
            index_status="processing",
        )
        self.database.insert_image(record)

        try:
            vector = self.embeddings.encode_image(stored.image_path)
            description = self.labeler.describe(vector)
            self.vector_index.add(record.id, vector)
        except (EmbeddingError, ValueError) as exc:
            failed = self.database.update_index_status(
                record.id,
                embedding_id=None,
                index_status="failed",
                description="Embedding failed. Check local CLIP dependencies and model weights.",
            )
            if failed is not None:
                record = failed
            if isinstance(exc, EmbeddingError):
                raise
            raise EmbeddingError(str(exc)) from exc

        indexed = self.database.update_index_status(
            record.id,
            embedding_id=record.id,
            index_status="indexed",
            description=description,
            embedding_model=self.embeddings.name,
            embedding_dimension=int(vector.shape[0]),
            embedding_norm=round(float((vector * vector).sum() ** 0.5), 6),
        )
        return indexed or record

    def list_images(self) -> list[ImageRecord]:
        return self.database.list_images()

    def get_image(self, image_id: str) -> ImageRecord:
        record = self.database.get_image(image_id)
        if record is None:
            raise ImageNotFoundError(image_id)
        return record

    def search(
        self,
        *,
        query_text: str,
        limit: int,
        captured_from: str | None,
        captured_to: str | None,
        location_text: str | None,
    ) -> list[tuple[ImageRecord, float]]:
        query_text = query_text.strip()
        if not query_text:
            raise ValueError("Search query cannot be empty.")
        if self.vector_index.count == 0:
            self._record_query(
                query_text=query_text,
                query_embedding=[],
                results=[],
                captured_from=captured_from,
                captured_to=captured_to,
                location_text=location_text,
            )
            return []

        vector = self.embeddings.encode_text(query_text)
        raw_results = self.vector_index.search(vector, limit=max(limit * 5, 30))
        vector_scores = {image_id: score for image_id, score in raw_results}
        records_by_id = self.database.get_images_by_ids(vector_scores)

        start = _parse_filter_date(captured_from, end_of_day=False)
        end = _parse_filter_date(captured_to, end_of_day=True)
        if start is None and end is None:
            start, end = _infer_date_range_from_query(query_text)
        location_filter = _clean_text(location_text)
        location_filter = location_filter.lower() if location_filter else None
        query_terms = _query_terms(query_text)

        candidates: dict[str, tuple[ImageRecord, float]] = {}
        for record in self.database.list_images():
            if record.index_status != "indexed":
                continue
            if not _record_in_time_range(record, start, end):
                continue
            if location_filter and location_filter not in _record_location_text(record):
                continue
            vector_score = vector_scores.get(record.id)
            metadata_score = _metadata_match_score(record, query_terms)
            if vector_score is None and metadata_score == 0:
                continue
            vector_component = max(0.0, float(vector_score or 0)) * 0.65
            combined_score = min(1.0, vector_component + metadata_score)
            candidates[record.id] = (record, combined_score)

        for image_id, score in raw_results:
            if image_id in candidates:
                continue
            record = records_by_id.get(image_id)
            if record is not None:
                candidates[image_id] = (record, float(score))

        results = sorted(candidates.values(), key=lambda item: item[1], reverse=True)
        results = [
            (record, score)
            for record, score in results
            if record.index_status == "indexed"
            and _record_in_time_range(record, start, end)
            and not (location_filter and location_filter not in _record_location_text(record))
        ][:limit]
        self._record_query(
            query_text=query_text,
            query_embedding=[round(float(value), 6) for value in vector.tolist()],
            results=[record.id for record, _ in results],
            captured_from=captured_from,
            captured_to=captured_to,
            location_text=location_text,
        )
        return results

    def list_queries(self, limit: int = 50) -> list[QueryRecord]:
        return self.database.list_queries(limit=limit)

    def list_tag_groups(self) -> list[tuple[str, list[str]]]:
        groups: dict[str, list[str]] = {}
        for record in self.database.list_images():
            if record.index_status != "indexed":
                continue
            for tag in _description_tags(record.description):
                groups.setdefault(tag, []).append(record.id)
        return sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))

    def image_url(self, record: ImageRecord) -> str:
        return f"/media/images/{Path(record.image_path).name}"

    def thumbnail_url(self, record: ImageRecord) -> str:
        return f"/media/thumbnails/{Path(record.thumbnail_path).name}"

    def _relative_to_data(self, path: Path) -> str:
        return path.resolve().relative_to(self.settings.data_dir.resolve()).as_posix()

    def _record_query(
        self,
        *,
        query_text: str,
        query_embedding: list[float],
        results: list[str],
        captured_from: str | None,
        captured_to: str | None,
        location_text: str | None,
    ) -> None:
        self.database.insert_query(
            QueryRecord(
                id=uuid4().hex,
                query_text=query_text,
                created_at=datetime.now(timezone.utc).isoformat(),
                query_embedding=query_embedding,
                result_ids=results,
                captured_from=_clean_text(captured_from),
                captured_to=_clean_text(captured_to),
                location_text=_clean_text(location_text),
            )
        )


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_filter_date(value: str | None, *, end_of_day: bool) -> datetime | None:
    value = _clean_text(value)
    if not value:
        return None
    try:
        if len(value) == 10:
            parsed_date = date.fromisoformat(value)
            boundary_time = time.max if end_of_day else time.min
            return datetime.combine(parsed_date, boundary_time)
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _infer_date_range_from_query(
    query_text: str,
    *,
    today: date | None = None,
) -> tuple[datetime | None, datetime | None]:
    text = query_text.lower()
    today = today or date.today()

    if _contains_any(text, ("今天", "今日", "today")):
        return _day_range(today)
    if _contains_any(text, ("昨天", "yesterday")):
        return _day_range(today - timedelta(days=1))
    if _contains_any(text, ("前天",)):
        return _day_range(today - timedelta(days=2))
    if _contains_any(text, ("本周", "这周", "this week")):
        start_day = today - timedelta(days=today.weekday())
        return _range_for_dates(start_day, today)
    if _contains_any(text, ("上周", "last week")):
        this_week_start = today - timedelta(days=today.weekday())
        start_day = this_week_start - timedelta(days=7)
        return _range_for_dates(start_day, start_day + timedelta(days=6))
    if _contains_any(text, ("最近一周", "近一周", "past week")):
        return _range_for_dates(today - timedelta(days=6), today)

    days = _extract_recent_days(text)
    if days is not None:
        return _range_for_dates(today - timedelta(days=days - 1), today)

    return None, None


def _extract_recent_days(text: str) -> int | None:
    patterns = (
        r"(?:最近|近)\s*(\d{1,3})\s*天",
        r"(?:last|past)\s+(\d{1,3})\s+days?",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        days = int(match.group(1))
        return max(1, min(days, 365))
    return None


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _day_range(day: date) -> tuple[datetime, datetime]:
    return _range_for_dates(day, day)


def _range_for_dates(start_day: date, end_day: date) -> tuple[datetime, datetime]:
    return datetime.combine(start_day, time.min), datetime.combine(end_day, time.max)


def _query_terms(query_text: str) -> set[str]:
    text = query_text.lower()
    terms = {
        token
        for token in re.findall(r"[a-z0-9]+", text)
        if len(token) >= 2 and token not in _SEARCH_STOPWORDS and not token.isdigit()
    }
    for cjk_text in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(cjk_text) <= 2:
            terms.add(cjk_text)
            continue
        terms.update(
            cjk_text[index : index + 2]
            for index in range(len(cjk_text) - 1)
            if cjk_text[index : index + 2] not in _CJK_STOPWORDS
        )
    return terms


_SEARCH_STOPWORDS = {
    "and",
    "are",
    "from",
    "last",
    "my",
    "of",
    "photo",
    "picture",
    "the",
    "this",
    "where",
    "with",
}

_CJK_STOPWORDS = {"我的", "在哪", "哪里", "照片", "拍的"}


def _metadata_match_score(record: ImageRecord, query_terms: set[str]) -> float:
    if not query_terms:
        return 0.0
    searchable_text = _record_search_text(record)
    matches = sum(1 for term in query_terms if term in searchable_text)
    return min(0.8, matches * 0.25)


def _record_search_text(record: ImageRecord) -> str:
    parts = [
        record.original_filename,
        record.user_notes,
        record.description,
        record.location_label,
    ]
    return " ".join(part for part in parts if part).lower()


def _description_tags(description: str | None) -> list[str]:
    if not description:
        return []
    match = re.search(r"semantic tags:\s*(.+?)(?:\.?$)", description, flags=re.IGNORECASE)
    if not match:
        return []
    tags = []
    for raw_tag in match.group(1).split(","):
        tag = raw_tag.strip().lower()
        if tag:
            tags.append(tag)
    return tags


def _record_datetime(record: ImageRecord) -> datetime | None:
    value = record.captured_at or record.upload_time
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _record_in_time_range(
    record: ImageRecord,
    start: datetime | None,
    end: datetime | None,
) -> bool:
    if start is None and end is None:
        return True
    record_time = _record_datetime(record)
    if record_time is None:
        return False
    if start is not None and record_time < start:
        return False
    if end is not None and record_time > end:
        return False
    return True


def _record_location_text(record: ImageRecord) -> str:
    parts = [
        record.location_label,
        str(record.latitude) if record.latitude is not None else None,
        str(record.longitude) if record.longitude is not None else None,
    ]
    return " ".join(part for part in parts if part).lower()
