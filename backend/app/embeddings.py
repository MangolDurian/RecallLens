from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
from PIL import Image

from .config import Settings


class EmbeddingError(RuntimeError):
    pass


class EmbeddingService(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def dimension(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def encode_image(self, path: Path) -> np.ndarray:
        raise NotImplementedError

    @abstractmethod
    def encode_text(self, text: str) -> np.ndarray:
        raise NotImplementedError

    def encode_texts(self, texts: list[str]) -> list[np.ndarray]:
        return [self.encode_text(text) for text in texts]


def normalize_vector(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if norm == 0:
        return vector
    return vector / norm


class HashEmbeddingService(EmbeddingService):
    """Small deterministic embedding backend for tests and offline UI demos."""

    _dimension = 512

    @property
    def name(self) -> str:
        return "hash"

    @property
    def dimension(self) -> int:
        return self._dimension

    def encode_image(self, path: Path) -> np.ndarray:
        try:
            image = Image.open(path).convert("RGB")
            pixels = np.asarray(image.resize((32, 32)), dtype=np.float32) / 255.0
        except Exception as exc:  # pragma: no cover - storage validation catches this first.
            raise EmbeddingError(f"Cannot embed image {path}") from exc

        mean_rgb = pixels.mean(axis=(0, 1))
        vector = self._hashed_seed(path.name)
        vector[:3] = mean_rgb
        vector[3] = float(mean_rgb.max() - mean_rgb.min())
        vector[4] = float(pixels.mean())
        return normalize_vector(vector)

    def encode_text(self, text: str) -> np.ndarray:
        lowered = text.lower()
        vector = self._hashed_seed(lowered)
        color_terms = {
            0: ("red", "红", "钥匙"),
            1: ("green", "绿"),
            2: ("blue", "蓝", "背包"),
        }
        for slot, terms in color_terms.items():
            if any(term in lowered for term in terms):
                vector[slot] += 3.0
        if any(term in lowered for term in ("bright", "light", "白")):
            vector[4] += 1.0
        if any(term in lowered for term in ("dark", "black", "黑")):
            vector[4] -= 1.0
        return normalize_vector(vector)

    def _hashed_seed(self, value: str) -> np.ndarray:
        digest = hashlib.sha256(value.encode("utf-8")).digest()
        repeated = (digest * ((self.dimension // len(digest)) + 1))[: self.dimension]
        vector = np.frombuffer(repeated, dtype=np.uint8).astype(np.float32)
        return ((vector - 127.5) / 127.5) * 0.03


class LocalClipEmbeddingService(EmbeddingService):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._preprocess = None
        self._tokenizer = None
        self._torch = None
        self._device = "cpu"

    @property
    def name(self) -> str:
        return f"clip:{self.settings.clip_model}:{self.settings.clip_pretrained}"

    @property
    def dimension(self) -> int:
        return self.settings.embedding_dimension

    def encode_image(self, path: Path) -> np.ndarray:
        self._ensure_loaded()
        try:
            image = Image.open(path).convert("RGB")
            image_tensor = self._preprocess(image).unsqueeze(0).to(self._device)
            with self._torch.no_grad():
                features = self._model.encode_image(image_tensor)
            return self._to_numpy(features)
        except Exception as exc:
            raise EmbeddingError(f"CLIP could not embed image {path}") from exc

    def encode_text(self, text: str) -> np.ndarray:
        self._ensure_loaded()
        try:
            tokens = self._tokenizer([text]).to(self._device)
            with self._torch.no_grad():
                features = self._model.encode_text(tokens)
            return self._to_numpy(features)
        except Exception as exc:
            raise EmbeddingError("CLIP could not embed query text.") from exc

    def encode_texts(self, texts: list[str]) -> list[np.ndarray]:
        self._ensure_loaded()
        try:
            tokens = self._tokenizer(texts).to(self._device)
            with self._torch.no_grad():
                features = self._model.encode_text(tokens)
            arrays = features.detach().cpu().numpy().astype(np.float32)
            return [normalize_vector(row) for row in arrays]
        except Exception as exc:
            raise EmbeddingError("CLIP could not embed semantic label text.") from exc

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return

        try:
            import open_clip
            import torch
        except ImportError as exc:
            raise EmbeddingError(
                "Local CLIP dependencies are missing. Install project dependencies "
                "with `uv pip install -r requirements-clip.txt`, or set "
                "RECALLLENS_EMBEDDER=hash for development."
            ) from exc

        if torch.backends.mps.is_available():
            self._device = "mps"
        elif torch.cuda.is_available():
            self._device = "cuda"
        else:
            self._device = "cpu"

        try:
            model, _, preprocess = open_clip.create_model_and_transforms(
                self.settings.clip_model,
                pretrained=self.settings.clip_pretrained,
                device=self._device,
            )
            model.eval()
            self._model = model
            self._preprocess = preprocess
            self._tokenizer = open_clip.get_tokenizer(self.settings.clip_model)
            self._torch = torch
        except Exception as exc:
            raise EmbeddingError(
                "Local CLIP model could not be loaded. Check model/pretrained names "
                "or ensure model weights are available."
            ) from exc

    @staticmethod
    def _to_numpy(features: object) -> np.ndarray:
        array = features.detach().cpu().numpy().astype(np.float32).reshape(-1)
        return normalize_vector(array)


def create_embedding_service(settings: Settings) -> EmbeddingService:
    if settings.embedder == "hash":
        return HashEmbeddingService()
    if settings.embedder == "clip":
        return LocalClipEmbeddingService(settings)
    raise ValueError(f"Unsupported RECALLLENS_EMBEDDER value: {settings.embedder}")
