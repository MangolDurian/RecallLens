from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError


class InvalidImageError(ValueError):
    pass


@dataclass(frozen=True)
class ImageMetadata:
    captured_at: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class StoredImage:
    id: str
    image_path: Path
    thumbnail_path: Path
    original_filename: str
    metadata: ImageMetadata


class ImageStorage:
    def __init__(self, images_dir: Path, thumbnails_dir: Path) -> None:
        self.images_dir = images_dir
        self.thumbnails_dir = thumbnails_dir
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, upload: UploadFile) -> StoredImage:
        data = await upload.read()
        if not data:
            raise InvalidImageError("Uploaded image is empty.")

        image_id = uuid4().hex
        original_filename = upload.filename or f"{image_id}.jpg"

        try:
            image = Image.open(BytesIO(data))
            image_format = image.format
            metadata = self._extract_metadata(image)
            image = ImageOps.exif_transpose(image)
            image.load()
        except (UnidentifiedImageError, OSError) as exc:
            raise InvalidImageError("Uploaded file is not a readable image.") from exc

        image = self._to_supported_mode(image)
        extension = self._extension_for(image_format, original_filename)
        if extension == ".jpg" and image.mode != "RGB":
            image = image.convert("RGB")
        image_path = self.images_dir / f"{image_id}{extension}"
        thumbnail_path = self.thumbnails_dir / f"{image_id}.jpg"

        image.save(image_path, quality=92)

        thumbnail = image.copy()
        thumbnail.thumbnail((720, 720))
        thumbnail.convert("RGB").save(thumbnail_path, "JPEG", quality=86)

        return StoredImage(
            id=image_id,
            image_path=image_path,
            thumbnail_path=thumbnail_path,
            original_filename=original_filename,
            metadata=metadata,
        )

    @staticmethod
    def _to_supported_mode(image: Image.Image) -> Image.Image:
        if image.mode in {"RGB", "RGBA", "L"}:
            return image
        return image.convert("RGB")

    @staticmethod
    def _extension_for(image_format: str | None, filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            return ".jpg" if suffix == ".jpeg" else suffix
        if image_format == "PNG":
            return ".png"
        if image_format == "WEBP":
            return ".webp"
        return ".jpg"

    @classmethod
    def _extract_metadata(cls, image: Image.Image) -> ImageMetadata:
        try:
            exif = image.getexif()
            if not exif:
                return ImageMetadata()

            captured_at = cls._extract_captured_at(exif)
            latitude, longitude = cls._extract_gps(exif)
            return ImageMetadata(
                captured_at=captured_at,
                latitude=latitude,
                longitude=longitude,
            )
        except Exception:
            return ImageMetadata()

    @staticmethod
    def _extract_captured_at(exif: Image.Exif) -> str | None:
        for tag in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
            value = exif.get(tag)
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="ignore")
            if not isinstance(value, str):
                continue
            value = value.strip()
            if not value:
                continue
            try:
                return datetime.strptime(value, "%Y:%m:%d %H:%M:%S").isoformat()
            except ValueError:
                return value
        return None

    @classmethod
    def _extract_gps(cls, exif: Image.Exif) -> tuple[float | None, float | None]:
        try:
            gps = exif.get_ifd(34853)
        except Exception:
            gps = exif.get(34853)
        if not isinstance(gps, dict):
            return None, None

        latitude = cls._gps_coordinate(gps.get(2), gps.get(1))
        longitude = cls._gps_coordinate(gps.get(4), gps.get(3))
        return latitude, longitude

    @classmethod
    def _gps_coordinate(cls, coordinate: Any, reference: Any) -> float | None:
        if coordinate is None or reference is None:
            return None
        if isinstance(reference, bytes):
            reference = reference.decode("ascii", errors="ignore")
        reference = str(reference).upper()
        try:
            degrees, minutes, seconds = coordinate
        except (TypeError, ValueError):
            return None

        decimal = (
            cls._rational_to_float(degrees)
            + cls._rational_to_float(minutes) / 60
            + cls._rational_to_float(seconds) / 3600
        )
        if reference in {"S", "W"}:
            decimal *= -1
        return decimal

    @staticmethod
    def _rational_to_float(value: Any) -> float:
        if isinstance(value, tuple) and len(value) == 2:
            numerator, denominator = value
            if float(denominator) == 0:
                raise ValueError("GPS rational denominator cannot be zero.")
            return float(numerator) / float(denominator)
        return float(value)
