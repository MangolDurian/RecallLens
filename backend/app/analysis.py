from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .embeddings import EmbeddingError, EmbeddingService, normalize_vector


@dataclass(frozen=True)
class LabelCandidate:
    name: str
    prompts: tuple[str, ...]


LABEL_CANDIDATES: tuple[LabelCandidate, ...] = (
    LabelCandidate("keys", ("a photo of keys", "a keychain", "钥匙")),
    LabelCandidate("charger", ("a phone charger", "a charging cable", "充电器")),
    LabelCandidate("passport", ("a passport", "travel documents", "护照")),
    LabelCandidate("wallet", ("a wallet", "a purse", "钱包")),
    LabelCandidate("backpack", ("a backpack", "a bag", "背包")),
    LabelCandidate("cup", ("a cup", "a mug", "a thermos", "保温杯")),
    LabelCandidate("phone", ("a mobile phone", "a smartphone", "手机")),
    LabelCandidate("laptop", ("a laptop computer", "笔记本电脑")),
    LabelCandidate("glasses", ("a pair of glasses", "眼镜")),
    LabelCandidate("book", ("a book", "a notebook", "书")),
    LabelCandidate("medicine", ("medicine", "a pill bottle", "药")),
    LabelCandidate("remote", ("a remote control", "遥控器")),
    LabelCandidate("desk", ("on a desk", "a desk scene", "书桌")),
    LabelCandidate("shelf", ("on a shelf", "a storage shelf", "架子")),
    LabelCandidate("drawer", ("inside a drawer", "抽屉")),
    LabelCandidate("entryway", ("an entryway", "near the door", "玄关")),
    LabelCandidate("kitchen", ("a kitchen counter", "厨房")),
    LabelCandidate("bedroom", ("a bedroom", "卧室")),
    LabelCandidate("office", ("an office", "办公室")),
    LabelCandidate("car", ("inside a car", "汽车内")),
    LabelCandidate("red", ("a red object", "red color", "红色")),
    LabelCandidate("green", ("a green object", "green color", "绿色")),
    LabelCandidate("blue", ("a blue object", "blue color", "蓝色")),
    LabelCandidate("black", ("a black object", "black color", "黑色")),
    LabelCandidate("white", ("a white object", "white color", "白色")),
)


class SemanticLabeler:
    def __init__(self, embeddings: EmbeddingService, *, limit: int = 5) -> None:
        self.embeddings = embeddings
        self.limit = limit
        self._prompt_cache: dict[str, np.ndarray] = {}
        self._labels_loaded = False

    def describe(self, image_vector: np.ndarray) -> str:
        tags = self.tags_for_image(image_vector)
        if not tags:
            return f"Visual embedding generated with {self.embeddings.name}."
        return f"Semantic tags: {', '.join(tags)}."

    def tags_for_image(self, image_vector: np.ndarray) -> list[str]:
        self._ensure_label_vectors()
        vector = normalize_vector(image_vector)
        scored: list[tuple[str, float]] = []
        for candidate in LABEL_CANDIDATES:
            prompt_scores = [
                float(vector @ self._encode_prompt(prompt)) for prompt in candidate.prompts
            ]
            scored.append((candidate.name, max(prompt_scores)))

        scored.sort(key=lambda item: item[1], reverse=True)
        return [name for name, _ in scored[: self.limit]]

    def _ensure_label_vectors(self) -> None:
        if self._labels_loaded:
            return
        prompts = [
            prompt
            for candidate in LABEL_CANDIDATES
            for prompt in candidate.prompts
            if prompt not in self._prompt_cache
        ]
        if not prompts:
            self._labels_loaded = True
            return
        try:
            vectors = self.embeddings.encode_texts(prompts)
        except EmbeddingError:
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper.
            raise EmbeddingError("Could not generate semantic labels for image.") from exc
        self._prompt_cache.update(zip(prompts, vectors, strict=True))
        self._labels_loaded = True

    def _encode_prompt(self, prompt: str) -> np.ndarray:
        cached = self._prompt_cache.get(prompt)
        if cached is not None:
            return cached
        try:
            vector = self.embeddings.encode_text(prompt)
        except EmbeddingError:
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper.
            raise EmbeddingError("Could not generate semantic labels for image.") from exc
        self._prompt_cache[prompt] = vector
        return vector
