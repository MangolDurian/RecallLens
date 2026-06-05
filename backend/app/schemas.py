from __future__ import annotations

from pydantic import BaseModel, Field


class LocationResponse(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    label: str | None = None


class ImageRecordResponse(BaseModel):
    id: str
    imageUrl: str
    thumbnailUrl: str
    originalFilename: str
    uploadTime: str
    capturedAt: str | None = None
    location: LocationResponse
    description: str | None = None
    userNotes: str | None = None
    embeddingId: str | None = None
    embeddingModel: str | None = None
    embeddingDimension: int | None = None
    embeddingNorm: float | None = None
    indexStatus: str


class ImageUploadRequest(BaseModel):
    imageBase64: str = Field(..., min_length=1)
    originalFilename: str | None = None
    note: str | None = None
    capturedAt: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    locationLabel: str | None = None


class SearchRequest(BaseModel):
    queryText: str = Field(..., min_length=1)
    limit: int = Field(default=5, ge=1, le=30)
    capturedFrom: str | None = None
    capturedTo: str | None = None
    locationText: str | None = None


class SearchResult(BaseModel):
    imageId: str
    score: float
    imageUrl: str
    thumbnailUrl: str
    originalFilename: str
    uploadTime: str
    capturedAt: str | None = None
    location: LocationResponse
    description: str | None = None
    userNotes: str | None = None
    embeddingModel: str | None = None
    embeddingDimension: int | None = None
    embeddingNorm: float | None = None
    indexStatus: str


class SearchResponse(BaseModel):
    queryText: str
    results: list[SearchResult]


class QueryRecordResponse(BaseModel):
    id: str
    queryText: str
    createdAt: str
    queryEmbedding: list[float]
    results: list[str]
    capturedFrom: str | None = None
    capturedTo: str | None = None
    locationText: str | None = None


class TagGroupResponse(BaseModel):
    tag: str
    count: int
    imageIds: list[str]


class HealthResponse(BaseModel):
    ok: bool
    embedder: str
    vectorBackend: str
    indexedImages: int
