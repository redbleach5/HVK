# -*- coding: utf-8 -*-
"""Страж JSON-схем: ответ модели «другой формы» не роняет агента.

Запуск: C:\\HVK\\.venv\\Scripts\\python.exe scripts\\verify_json_schemas.py

Без LLM и без сети: берём каждую схему, которую заполняет мозг, и
прогоняем реальные варианты ответа — строку вместо объекта, объект вместо
списка, словарь вместо строки. Если модель ответит так (а qwen3.6 отвечает),
агент должен продолжить работу, а не падать на ValidationError.

Провал = схема жёстко ждёт одну форму. Тогда автор увидит «Не получилось»,
хотя модель ответила по смыслу верно.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.audience import _AudienceInsightLlm, _AudienceLlmOut  # noqa: E402
from app.agents.base import ensure_why  # noqa: E402
from app.agents.concierge import _ConciergeLlmOut  # noqa: E402
from app.agents.editor import _EditLlmOut  # noqa: E402
from app.agents.ideas import _IdeaBatchLlm, _IdeaCardLlm  # noqa: E402
from app.agents.photo import _PhotoLlmOut  # noqa: E402
from app.schemas.common import WhyBlockLlm, as_str_list  # noqa: E402

PROBLEMS: list[str] = []


def check(name: str, fn) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        PROBLEMS.append(f"{name}: {type(exc).__name__}: {exc}")
        print(f"ПРОВАЛ {name}: {type(exc).__name__}: {str(exc)[:200]}")
        return
    print(f"ок    {name}")


def test_as_str_list() -> None:
    assert as_str_list("строка") == ["строка"]
    assert as_str_list({"action": "Поделиться"}) == ["Поделиться"]
    assert as_str_list(["а", {"b": "в"}]) == ["а", "в"]
    assert as_str_list(None) == []
    assert as_str_list([]) == []
    assert as_str_list([None, "  "]) == []


def test_why_shapes() -> None:
    assert WhyBlockLlm.model_validate({"summary": "s"}).summary == "s"
    assert WhyBlockLlm.model_validate("по сезону").summary == "по сезону"
    assert WhyBlockLlm.model_validate(None).summary == ""
    assert WhyBlockLlm.model_validate({}).related_posts == []
    parsed = WhyBlockLlm.model_validate({"related_posts": "#4, #7"})
    assert parsed.related_posts == ["#4", "#7"], parsed.related_posts


def test_ensure_why_accepts_llm_block() -> None:
    why = ensure_why(WhyBlockLlm(summary="моя причина"), "фолбэк")
    assert why.summary == "моя причина", why.summary
    assert why.seasonality, "сезонность должна подставиться"
    assert ensure_why("строка", "фолбэк").summary == "строка"
    assert ensure_why(None, "фолбэк").summary == "фолбэк"


def test_audience_string_lists() -> None:
    out = _AudienceLlmOut.model_validate(
        {
            "what_works": {"action": "Показывать процесс", "format": "пост"},
            "frequent_questions": "Сколько стоит?",
            "unmet_needs": None,
            "recommendations": ["больше тихих кадров"],
            "insights": {"1": {"title": "Тема", "why": "потому что"}},
            "why": "по статистике",
            "portrait": "молодые мамы",
        }
    )
    assert out.what_works, "словарь должен стать строкой"
    assert out.frequent_questions == ["Сколько стоит?"]
    assert out.unmet_needs == []
    assert len(out.insights) == 1
    insight = _AudienceInsightLlm.model_validate({"title": "t", "why": None})
    assert insight.why.summary == ""


def test_editor_soft_lists() -> None:
    out = _EditLlmOut.model_validate(
        {
            "revised_text": "текст",
            "edits": "переставила абзацы",
            "alternative_openings": {"first": "Кажется, осень…"},
            "why": "бережно",
        }
    )
    assert out.revised_text == "текст"
    assert out.edits, "правка строкой не должна пропасть"
    assert out.alternative_openings, "вариант начала словарём не должен пропасть"


def test_editor_live_bug() -> None:
    """Реальный сбой 02:05 — /text/edit отдал 502 из-за формы ответа модели."""
    out = _EditLlmOut.model_validate(
        {
            "revised_text": "Осенний текст",
            "edits": [{"original": "было", "revised": "стало", "explanation": "мягче"}],
            "alternative_openings": [
                {"text": "Осень в самом разгаре"},
                {"text": "Просто мысль, не читателя"},
            ],
            "why": {"summary": "бережно", "related_posts": [136, 38]},
        }
    )
    assert len(out.alternative_openings) == 2, "начала объектами должны стать строками"
    assert out.alternative_openings[0] == "Осень в самом разгаре"
    assert out.why.related_posts == ["136", "38"], "id постов числами — тоже ссылки"
    # правка, целиком пришедшая текстом
    crop = _EditLlmOut.model_validate(
        {"revised_text": "т", "edits": ["убрать лишнее"], "why": "просто"}
    )
    assert crop.edits and crop.edits[0].revised == "убрать лишнее"


def test_concierge_why_string() -> None:
    out = _ConciergeLlmOut.model_validate(
        {"category": "compliment", "draft_reply": "Спасибо 🤍", "why": "тёплое ЛС"}
    )
    assert out.why.summary == "тёплое ЛС"
    assert out.related_post is None


def test_photo_soft() -> None:
    out = _PhotoLlmOut.model_validate(
        {
            "verdict": "спокойный кадр",
            "scores": {
                "atmosphere": "7/10",
                "composition": 6,
                "light": 8,
                "palette": 7,
                "storytelling": "12",
                "aesthetic": "не число",
            },
            "advice": "чуть больше воздуха",
            "caption_direction": "про утро",
            "why": {"summary": "в эстетике блога"},
            "best_in_series": "2",
        }
    )
    assert out.advice, "совет строкой должен разложиться в список"
    assert out.best_in_series == 2
    assert out.scores.atmosphere == 7, "«7/10» должно стать 7"
    assert out.scores.storytelling == 10, "12 — за потолком 10"
    assert out.scores.aesthetic_fit == 5, "мусор — нейтральная пятёрка"
    # оценки отсутствуют целиком — разбор кадра всё равно не падает
    assert _PhotoLlmOut.model_validate(
        {"verdict": "v", "scores": {}, "why": "строка"}
    ).scores.light == 5


def test_ideas_single_object() -> None:
    one = _IdeaBatchLlm.model_validate(
        {"ideas": {"theme": "тихий вечер", "format": "пост", "why": "сезон"}}
    )
    assert len(one.ideas) == 1
    assert one.ideas[0].theme == "тихий вечер"
    numbered = _IdeaBatchLlm.model_validate(
        {"ideas": {"1": {"theme": "а"}, "2": {"theme": "б"}}}
    )
    assert [i.theme for i in numbered.ideas] == ["а", "б"]
    card = _IdeaCardLlm.model_validate({"theme": "t", "why": "строка"})
    assert card.why.summary == "строка"


def test_voice_schemas() -> None:
    import importlib

    module = importlib.import_module("app.voice.profile")
    source = Path(module.__file__).read_text(encoding="utf-8")
    if "as_str_list" not in source:
        raise AssertionError("профиль голоса снова жёсткий: нет as_str_list")
    for field in ("lexicon", "forbidden_vibes", "sample_phrases", "shades"):
        if field not in source:
            raise AssertionError(f"поле {field} пропало из профиля голоса")

    from app.voice.detector import VoiceCheck

    check_obj = VoiceCheck.model_validate(
        {"in_voice": True, "what_stands_out": "звучит", "details": {"1": "живое «кажется»"}}
    )
    assert check_obj.details, "замечания словарём должны стать списком"


def test_digest_and_soften() -> None:
    """Утреннее резюме: highlights строкой и soften на пути клиента."""
    from app.llm.soften import soften
    from app.scheduler.jobs import _DigestLlm

    out = _DigestLlm.model_validate(
        soften(_DigestLlm, {"body": "Сегодня тихо", "highlights": "тёплый свет, чай"})
    )
    assert out.highlights, "заметка строкой должна стать объектом"
    assert out.highlights[0]["text"] == "тёплый свет, чай"

    body = _DigestLlm.model_validate(
        soften(_DigestLlm, {"body": {"morning": "тихо"}, "highlights": []})
    )
    assert isinstance(body.body, str) and body.body

    numbers = _DigestLlm.model_validate(
        soften(_DigestLlm, {"body": "т", "highlights": {"1": {"text": "а"}, "2": {"text": "б"}}})
    )
    assert [h["text"] for h in numbers.highlights] == ["а", "б"]


def main() -> int:
    print("=== схемы, которые заполняет мозг ===")
    check("as_str_list", test_as_str_list)
    check("why: строка/пустота/объект", test_why_shapes)
    check("ensure_why принимает why модели", test_ensure_why_accepts_llm_block)
    check("аудитория: четыре списка", test_audience_string_lists)
    check("редактор: правки и начала", test_editor_soft_lists)
    check("редактор: живой сбой 502", test_editor_live_bug)
    check("консьерж: why строкой", test_concierge_why_string)
    check("фото: совет строкой", test_photo_soft)
    check("идеи: одна идея объектом", test_ideas_single_object)
    check("голос: списки и оттенки", test_voice_schemas)
    check("дайджест и soften", test_digest_and_soften)

    print()
    if PROBLEMS:
        for item in PROBLEMS:
            print("ПРОВАЛ:", item)
        return 1
    print("ОК: любая форма ответа модели приводит к рабочему агенту")
    return 0


if __name__ == "__main__":
    sys.exit(main())