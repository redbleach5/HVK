"""Локальный эмбеддер архива: multilingual-e5-small через onnxruntime.

Замена дефолтной английской MiniLM: e5 держит русский смысл
(«чаю/чаем», «доченька/дочь», «накинула/надела»). Работает на CPU,
файлы модели кладёт scripts/fetch_e5_onnx.py в data/models/e5-small-onnx.
Файлов нет — e5_available() False, проект живёт на старом эмбеддере.
В рантайме ничего не качает и не требует torch.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)

_MAX_TOKENS = 512
_PREFIX_QUERY = "query: "
_PREFIX_PASSAGE = "passage: "

_embedder: Optional["E5Embedder"] = None
_available: Optional[bool] = None


def _model_dir() -> Path:
    settings = get_settings()
    return settings.resolve_path(settings.embedding_model_dir)


def e5_available() -> bool:
    """Модель и токенизатор на месте? Решается один раз за процесс."""
    global _available
    if _available is None:
        directory = _model_dir()
        _available = (directory / "model.onnx").exists() and (
            directory / "tokenizer.json"
        ).exists()
        logger.info(
            "эмбеддер e5 %s (%s)",
            "доступен" if _available else "не найден",
            directory,
        )
    return _available


class E5Embedder:
    """Вектора смысла. query=True — для вопросов, False — для постов."""

    def __init__(self) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        directory = _model_dir()
        model_path = directory / "model.onnx"
        if not model_path.exists():
            model_path = directory / "model_quantized.onnx"
        if not model_path.exists():
            raise FileNotFoundError(f"нет модели e5 в {directory}")
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=_MAX_TOKENS)
        options = ort.SessionOptions()
        # Скромно по ядрам: пока мозг отвечает, эмбеддер не должен мешать.
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(
            str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self._needs_token_type_ids = any(
            item.name == "token_type_ids" for item in self.session.get_inputs()
        )
        logger.info("эмбеддер e5 загружен: %s", model_path.name)

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        """Нормированные вектора. Пустой список на входе — пустой на выходе."""
        if not texts:
            return []
        prefix = _PREFIX_QUERY if query else _PREFIX_PASSAGE
        prepared = [prefix + (text or "").strip() for text in texts]
        encoded = self.tokenizer.encode_batch(prepared, add_special_tokens=True)
        width = max(len(enc.ids) for enc in encoded)
        input_ids = np.zeros((len(encoded), width), dtype=np.int64)
        attention = np.zeros((len(encoded), width), dtype=np.int64)
        for i, enc in enumerate(encoded):
            span = len(enc.ids)
            input_ids[i, :span] = enc.ids
            attention[i, :span] = enc.attention_mask
        feeds: dict[str, np.ndarray] = {
            "input_ids": input_ids,
            "attention_mask": attention,
        }
        if self._needs_token_type_ids:
            feeds["token_type_ids"] = np.zeros_like(input_ids)
        out = self.session.run(None, feeds)[0]
        if out.ndim == 2:
            vectors = out.astype(np.float32)
        else:
            mask = attention[:, :, None].astype(np.float32)
            summed = (out.astype(np.float32) * mask).sum(axis=1)
            counts = np.clip(mask.sum(axis=1), 1e-9, None)
            vectors = summed / counts
        norms = np.clip(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9, None)
        return (vectors / norms).astype(np.float32).tolist()


def get_embedder() -> E5Embedder:
    """Один эмбеддер на процесс, лениво."""
    global _embedder
    if _embedder is None:
        _embedder = E5Embedder()
    return _embedder
