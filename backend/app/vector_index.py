from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .embeddings import normalize_vector

try:  # pragma: no cover - depends on optional native package availability.
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None


class VectorIndex:
    def __init__(self, index_dir: Path, dimension: int) -> None:
        self.index_dir = index_dir
        self.dimension = dimension
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.ids_path = self.index_dir / "ids.json"
        self.faiss_path = self.index_dir / "images.faiss"
        self.numpy_path = self.index_dir / "vectors.npy"
        self.ids: list[str] = []
        self._vectors = np.empty((0, self.dimension), dtype=np.float32)
        self._faiss_index = None
        self._load()

    @property
    def backend_name(self) -> str:
        return "faiss" if self._faiss_index is not None else "numpy"

    @property
    def count(self) -> int:
        return len(self.ids)

    def add(self, image_id: str, vector: np.ndarray) -> None:
        vector = self._prepare_vector(vector)
        if image_id in self.ids:
            self._replace(image_id, vector)
        else:
            self.ids.append(image_id)
            self._vectors = np.vstack([self._vectors, vector.reshape(1, -1)])
            if self._faiss_index is not None:
                self._faiss_index.add(vector.reshape(1, -1))
        self.persist()

    def search(self, vector: np.ndarray, limit: int) -> list[tuple[str, float]]:
        if not self.ids:
            return []

        vector = self._prepare_vector(vector)
        limit = max(1, min(limit, len(self.ids)))
        if self._faiss_index is not None:
            scores, positions = self._faiss_index.search(vector.reshape(1, -1), limit)
            return [
                (self.ids[int(position)], float(score))
                for score, position in zip(scores[0], positions[0], strict=False)
                if int(position) >= 0
            ]

        scores = self._vectors @ vector
        positions = np.argsort(-scores)[:limit]
        return [(self.ids[int(position)], float(scores[int(position)])) for position in positions]

    def persist(self) -> None:
        self.ids_path.write_text(json.dumps(self.ids, ensure_ascii=False, indent=2), "utf-8")
        np.save(self.numpy_path, self._vectors)
        if self._faiss_index is not None and faiss is not None:
            faiss.write_index(self._faiss_index, str(self.faiss_path))

    def _load(self) -> None:
        if self.ids_path.exists():
            self.ids = json.loads(self.ids_path.read_text("utf-8"))

        if self.numpy_path.exists():
            vectors = np.load(self.numpy_path)
            if vectors.ndim == 2 and vectors.shape[1] == self.dimension:
                self._vectors = vectors.astype(np.float32)

        if len(self.ids) != len(self._vectors):
            self.ids = self.ids[: len(self._vectors)]

        if faiss is not None:
            if self.faiss_path.exists():
                loaded = faiss.read_index(str(self.faiss_path))
                if loaded.d == self.dimension and loaded.ntotal == len(self.ids):
                    self._faiss_index = loaded
                    return
            self._faiss_index = faiss.IndexFlatIP(self.dimension)
            if len(self._vectors):
                self._faiss_index.add(self._vectors)

    def _replace(self, image_id: str, vector: np.ndarray) -> None:
        position = self.ids.index(image_id)
        self._vectors[position] = vector
        if faiss is not None:
            self._faiss_index = faiss.IndexFlatIP(self.dimension)
            self._faiss_index.add(self._vectors)

    def _prepare_vector(self, vector: np.ndarray) -> np.ndarray:
        vector = normalize_vector(vector)
        if vector.shape[0] != self.dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.dimension}, got {vector.shape[0]}"
            )
        return vector.astype(np.float32)

