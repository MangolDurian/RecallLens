from __future__ import annotations

import base64
import binascii
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .database import Database
from .embeddings import EmbeddingError, create_embedding_service
from .schemas import (
    HealthResponse,
    ImageRecordResponse,
    ImageUploadRequest,
    LocationResponse,
    QueryRecordResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    TagGroupResponse,
)
from .service import ImageNotFoundError, RecallLensService
from .storage import ImageStorage, InvalidImageError
from .vector_index import VectorIndex


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_APP_DIR = PROJECT_ROOT / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    service = RecallLensService(
        settings=settings,
        database=Database(settings.database_path),
        storage=ImageStorage(settings.images_dir, settings.thumbnails_dir),
        embeddings=create_embedding_service(settings),
        vector_index=VectorIndex(settings.index_dir, settings.embedding_dimension),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        settings.images_dir.mkdir(parents=True, exist_ok=True)
        settings.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        settings.index_dir.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(title="RecallLens", version="0.1.0", lifespan=lifespan)
    app.state.recalllens_service = service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/media/images", StaticFiles(directory=settings.images_dir), name="images")
    app.mount(
        "/media/thumbnails",
        StaticFiles(directory=settings.thumbnails_dir),
        name="thumbnails",
    )
    app.mount("/app", StaticFiles(directory=STATIC_APP_DIR, html=True), name="static_app")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/app/")

    @app.get("/api/health", response_model=HealthResponse)
    def health(service: RecallLensService = Depends(get_service)) -> HealthResponse:
        return HealthResponse(
            ok=True,
            embedder=service.embeddings.name,
            vectorBackend=service.vector_index.backend_name,
            indexedImages=service.vector_index.count,
        )

    @app.post("/api/images", response_model=ImageRecordResponse, status_code=201)
    async def upload_image(
        request: Request,
        service: RecallLensService = Depends(get_service),
    ) -> ImageRecordResponse:
        try:
            payload = await parse_upload_request(request)
            record = await service.add_image(
                payload.upload,
                note=payload.note,
                captured_at=payload.captured_at,
                latitude=payload.latitude,
                longitude=payload.longitude,
                location_label=payload.location_label,
            )
        except InvalidImageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            if "python-multipart" in str(exc):
                raise HTTPException(
                    status_code=415,
                    detail=(
                        "Multipart uploads require python-multipart. "
                        "Use JSON imageBase64 upload or install project dependencies."
                    ),
                ) from exc
            raise
        except EmbeddingError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return to_image_response(service, record)

    @app.get("/api/images", response_model=list[ImageRecordResponse])
    def list_images(
        service: RecallLensService = Depends(get_service),
    ) -> list[ImageRecordResponse]:
        return [to_image_response(service, record) for record in service.list_images()]

    @app.get("/api/images/{image_id}", response_model=ImageRecordResponse)
    def get_image(
        image_id: str,
        service: RecallLensService = Depends(get_service),
    ) -> ImageRecordResponse:
        try:
            record = service.get_image(image_id)
        except ImageNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Image not found.") from exc
        return to_image_response(service, record)

    @app.post("/api/search", response_model=SearchResponse)
    def search(
        request: SearchRequest,
        service: RecallLensService = Depends(get_service),
    ) -> SearchResponse:
        try:
            matches = service.search(
                query_text=request.queryText,
                limit=request.limit,
                captured_from=request.capturedFrom,
                captured_to=request.capturedTo,
                location_text=request.locationText,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except EmbeddingError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        return SearchResponse(
            queryText=request.queryText,
            results=[
                SearchResult(
                    imageId=record.id,
                    score=score,
                    imageUrl=service.image_url(record),
                    thumbnailUrl=service.thumbnail_url(record),
                    originalFilename=record.original_filename,
                    uploadTime=record.upload_time,
                    capturedAt=record.captured_at,
                    location=LocationResponse(
                        latitude=record.latitude,
                        longitude=record.longitude,
                        label=record.location_label,
                    ),
                    description=record.description,
                    userNotes=record.user_notes,
                    embeddingModel=record.embedding_model,
                    embeddingDimension=record.embedding_dimension,
                    embeddingNorm=record.embedding_norm,
                    indexStatus=record.index_status,
                )
                for record, score in matches
            ],
        )

    @app.get("/api/queries", response_model=list[QueryRecordResponse])
    def list_queries(
        limit: int = 50,
        service: RecallLensService = Depends(get_service),
    ) -> list[QueryRecordResponse]:
        limit = max(1, min(limit, 200))
        return [
            QueryRecordResponse(
                id=record.id,
                queryText=record.query_text,
                createdAt=record.created_at,
                queryEmbedding=record.query_embedding,
                results=record.result_ids,
                capturedFrom=record.captured_from,
                capturedTo=record.captured_to,
                locationText=record.location_text,
            )
            for record in service.list_queries(limit=limit)
        ]

    @app.get("/api/tags", response_model=list[TagGroupResponse])
    def list_tags(
        service: RecallLensService = Depends(get_service),
    ) -> list[TagGroupResponse]:
        return [
            TagGroupResponse(tag=tag, count=len(image_ids), imageIds=image_ids)
            for tag, image_ids in service.list_tag_groups()
        ]

    return app


def get_service(request: Request) -> RecallLensService:
    return request.app.state.recalllens_service


@dataclass(frozen=True)
class ParsedUpload:
    upload: "BytesUpload | object"
    note: str | None
    captured_at: str | None
    latitude: float | None
    longitude: float | None
    location_label: str | None


@dataclass
class BytesUpload:
    filename: str
    data: bytes

    async def read(self) -> bytes:
        return self.data


async def parse_upload_request(request: Request) -> ParsedUpload:
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("application/json"):
        return await parse_json_upload(request)
    if content_type.startswith("multipart/form-data"):
        return await parse_multipart_upload(request)
    raise ValueError("Upload must be application/json or multipart/form-data.")


async def parse_json_upload(request: Request) -> ParsedUpload:
    body = ImageUploadRequest.model_validate(await request.json())
    filename = body.originalFilename or "upload.jpg"
    return ParsedUpload(
        upload=BytesUpload(filename=filename, data=decode_image_base64(body.imageBase64)),
        note=body.note,
        captured_at=body.capturedAt,
        latitude=body.latitude,
        longitude=body.longitude,
        location_label=body.locationLabel,
    )


async def parse_multipart_upload(request: Request) -> ParsedUpload:
    try:
        form = await request.form()
    except Exception as exc:
        if "python-multipart" in str(exc):
            raise RuntimeError("python-multipart is required for multipart uploads.") from exc
        raise
    image = form.get("image")
    if image is None or not hasattr(image, "read"):
        raise ValueError("Multipart upload requires an image file field.")
    return ParsedUpload(
        upload=image,
        note=_form_text(form.get("note")),
        captured_at=_form_text(form.get("capturedAt")),
        latitude=_form_float(form.get("latitude")),
        longitude=_form_float(form.get("longitude")),
        location_label=_form_text(form.get("locationLabel")),
    )


def decode_image_base64(value: str) -> bytes:
    if "," in value and value.lower().startswith("data:"):
        value = value.split(",", 1)[1]
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("imageBase64 is not valid base64.") from exc


def _form_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _form_float(value: object) -> float | None:
    text = _form_text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric form value: {text}") from exc


def to_image_response(
    service: RecallLensService,
    record,
) -> ImageRecordResponse:
    return ImageRecordResponse(
        id=record.id,
        imageUrl=service.image_url(record),
        thumbnailUrl=service.thumbnail_url(record),
        originalFilename=record.original_filename,
        uploadTime=record.upload_time,
        capturedAt=record.captured_at,
        location=LocationResponse(
            latitude=record.latitude,
            longitude=record.longitude,
            label=record.location_label,
        ),
        description=record.description,
        userNotes=record.user_notes,
        embeddingId=record.embedding_id,
        embeddingModel=record.embedding_model,
        embeddingDimension=record.embedding_dimension,
        embeddingNorm=record.embedding_norm,
        indexStatus=record.index_status,
    )


app = create_app()
