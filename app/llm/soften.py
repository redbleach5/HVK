# -*- coding: utf-8 -*-
"""Мягкая подгонка JSON модели под схему агента.

Зачем: мозг (qwen3.6) почти всегда отвечает правильно, но иногда меняет форму —
`portrait` приходит объектом с полями, список — объектом с нумерацией, строка —
словарём. Ждать от модели идеальной формы нельзя: хирургически выкидывать такие
ответы значит терять рабочие ответы целиком (живой сбой: POST /text/edit → 502
на `why.related_posts.0`).

Здесь форма приводится к схеме ДО pydantic: строковое поле получает читаемый
текст, список строк — список, список объектов — список объектов. Смысл ответа
не меняется, агент не падает.
"""

from __future__ import annotations

import types
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from app.schemas.common import as_obj_list, as_str_list


def _text(value: Any) -> str:
    """Читаемый текст из строки, списка или объекта с подписями."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        parts: list[str] = []
        for item in value.values():
            piece = _text(item)
            if piece:
                parts.append(piece)
        return ", ".join(parts)
    if isinstance(value, (list, tuple)):
        parts = [_text(item) for item in value]
        return ", ".join(part for part in parts if part)
    if value is None:
        return ""
    return str(value).strip()


def _is_str(ann: Any) -> bool:
    return ann is str


def _inner(ann: Any) -> Any:
    """Внутренний тип Optional/Union — берём первый содержательный."""
    if get_origin(ann) in (Union, types.UnionType):
        for arg in get_args(ann):
            if arg is not type(None):
                return arg
    return ann


def soften(schema: type[BaseModel], data: Any) -> Any:
    """Приводит разобранный JSON к форме схемы; неизвестное оставляет как есть."""
    if not isinstance(data, dict):
        return data
    out: dict[str, Any] = dict(data)
    for name, field in schema.model_fields.items():
        if name not in out:
            continue
        value = out[name]
        ann = _inner(field.annotation)
        if _is_str(ann):
            if isinstance(value, (dict, list, tuple)):
                out[name] = _text(value)
            elif value is None:
                out[name] = ""
            continue
        origin = get_origin(ann)
        if origin is list:
            args = get_args(ann)
            inner = _inner(args[0]) if args else None
            if isinstance(inner, type) and issubclass(inner, BaseModel):
                items = as_obj_list(value)
                out[name] = [
                    soften(inner, item) if isinstance(item, dict) else item for item in items
                ]
            elif inner is dict or get_origin(inner) is dict:
                # Список объектов: строка от модели становится {"text": ...},
                # иначе {"1": {...}} — коллекцией.
                out[name] = [
                    item if isinstance(item, dict) else {"text": _text(item)}
                    for item in as_obj_list(value)
                ]
            else:
                out[name] = as_str_list(value)
            continue
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            if isinstance(value, dict):
                out[name] = soften(ann, value)
            elif isinstance(value, str):
                out[name] = {}
            continue
    return out