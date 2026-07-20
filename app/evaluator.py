"""Проверка описания картинки, которое написал пользователь.

Это ядро ассоциативной механики: человек видит сцену, описывает её своими
словами и тем самым вспоминает слово вместе с ситуацией, а не заучивает пару
«слово — перевод».

Почему проверка дешёвая. Картинку мы сгенерировали сами и храним её описание
в Word.scene_prompt. То есть эталон известен заранее, и сравнивать ответ с ним
может обычная ТЕКСТОВАЯ модель — дорогая мультимодальная не нужна вовсе.

Оценка намеренно МЯГКАЯ. Главное — уместно употребить целевое слово и передать
смысл сцены; ошибки грамматики попадают в отдельное поле и показываются
пользователю как подсказка, но не понижают оценку и не откатывают повторы.
Иначе новичок на A1 будет получать «неверно» за артикли и бросит.

Как и остальные внешние модули, наружу не бросает исключений: при любой
проблеме отдаёт результат офлайн-проверки (см. _offline_verdict).
"""

from __future__ import annotations

import json
import logging
import os
import re

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_MODEL = "llama-3.3-70b-versatile"
_TIMEOUT_SECONDS = 20.0

# Порог зачёта: 2 и выше считаем успешным повтором.
#   0 — слово не использовано или сцена не понята
#   1 — слово есть, но смысл сцены передан плохо
#   2 — слово уместно и сцена передана
#   3 — то же плюс живой, точный английский
PASS_GRADE = 2


def _build_prompt(word: str, translation: str, phrase: str,
                  scene: str, level: str, answer: str) -> str:
    return (
        f"You are a kind English teacher checking a vocabulary exercise.\n\n"
        f"The learner (CEFR level {level}) was shown a picture and asked to "
        f"describe it in English, using the target word.\n\n"
        f"Target word: \"{word}\" (Russian meaning: \"{translation}\")\n"
        f"What the picture actually shows: \"{scene}\"\n"
        f"Reference phrase the picture was drawn from: \"{phrase}\"\n\n"
        f"The learner wrote:\n\"{answer}\"\n\n"
        f"Grade from 0 to 3:\n"
        f"  0 - the target word is missing or used in a wrong meaning;\n"
        f"  1 - the word is used correctly but the description misses the scene;\n"
        f"  2 - the word is used correctly and the scene is conveyed;\n"
        f"  3 - same as 2, plus natural and precise English.\n\n"
        f"IMPORTANT grading rules:\n"
        f"- Judge MEANING, not grammar. Do NOT lower the grade for articles,\n"
        f"  spelling, word order or tense mistakes.\n"
        f"- The learner does not have to match the reference phrase word for\n"
        f"  word. Any description that fits the picture counts.\n"
        f"- Be generous: this is a beginner practising, not an exam.\n\n"
        f"Write feedback in RUSSIAN, warm and short (one or two sentences).\n"
        f"List grammar issues separately in Russian, as short hints — at most\n"
        f"three, and only real mistakes. If there are none, use an empty list.\n"
        f"Give one improved English version of the learner's sentence.\n\n"
        f"Respond with ONLY a JSON object in this exact shape:\n"
        f'{{"grade": 0, "used_word": true, "feedback_ru": "...", '
        f'"grammar_ru": ["..."], "better_en": "..."}}'
    )


def _word_is_used(word: str, answer: str) -> bool:
    """Есть ли целевое слово в ответе — грубо, по корню.

    Отрезаем у слова хвост в пару букв, чтобы поймать формы: build → building,
    city → cities. Это офлайн-эвристика, от неё не требуется точность
    морфологического анализатора.
    """
    w = (word or "").strip().lower()
    a = (answer or "").lower()
    if not w or not a:
        return False
    if w in a:
        return True
    stem = w[:-2] if len(w) > 5 else w[:-1] if len(w) > 3 else w
    return bool(stem) and stem in a


def _offline_verdict(word: str, answer: str) -> dict:
    """Проверка без ИИ: слово употреблено и написано хотя бы несколько слов.

    Работает, когда Groq недоступен. Намеренно снисходительна — лучше зачесть
    лишнее, чем наказать человека за то, что у нас отвалился внешний сервис.
    """
    used = _word_is_used(word, answer)
    long_enough = len(re.findall(r"\w+", answer or "")) >= 3
    grade = 2 if (used and long_enough) else (1 if used else 0)
    return {
        "grade": grade,
        "used_word": used,
        "feedback_ru": (
            "Проверка ИИ сейчас недоступна, засчитали по употреблению слова."
            if used else
            "Проверка ИИ сейчас недоступна, а целевого слова в ответе не нашлось."
        ),
        "grammar_ru": [],
        "better_en": "",
        "offline": True,
    }


async def evaluate_description(word: str, translation: str, phrase: str,
                               scene: str, level: str, answer: str) -> dict:
    """Разбор описания. Всегда возвращает валидный словарь.

    Ключи: grade (0..3), used_word, feedback_ru, grammar_ru (список),
    better_en, offline (True — оценка получена без ИИ).
    """
    answer = (answer or "").strip()
    if not answer:
        return {
            "grade": 0, "used_word": False,
            "feedback_ru": "Пустой ответ — опишите, что происходит на картинке.",
            "grammar_ru": [], "better_en": "", "offline": True,
        }

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY не задан — оцениваем описание офлайн.")
        return _offline_verdict(word, answer)

    try:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=api_key, timeout=_TIMEOUT_SECONDS)
        resp = await client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": _build_prompt(
                word, translation, phrase, scene, level, answer)}],
            response_format={"type": "json_object"},
            # Низкая температура: оценка должна быть предсказуемой, в отличие
            # от генерации фраз, где разнообразие как раз нужно.
            temperature=0.2,
        )
        content = resp.choices[0].message.content if resp.choices else None
        if not content:
            return _offline_verdict(word, answer)

        data = json.loads(content)

        # Приводим к нашему контракту: модель могла вернуть строку вместо
        # числа, один совет вместо списка или вовсе пропустить поле.
        grade = int(data.get("grade", 0))
        grade = max(0, min(grade, 3))
        grammar = data.get("grammar_ru") or []
        if isinstance(grammar, str):
            grammar = [grammar]

        return {
            "grade": grade,
            # Доверяй, но проверяй: если модель уверяет, что слова нет, а оно
            # в тексте есть — верим тексту.
            "used_word": bool(data.get("used_word")) or _word_is_used(word, answer),
            "feedback_ru": (data.get("feedback_ru") or "").strip(),
            "grammar_ru": [str(g).strip() for g in grammar[:3] if str(g).strip()],
            "better_en": (data.get("better_en") or "").strip(),
            "offline": False,
        }

    except json.JSONDecodeError as e:
        logger.warning("Не удалось распарсить оценку от Groq (слово '%s'): %s", word, e)
        return _offline_verdict(word, answer)
    except Exception as e:
        logger.warning("Ошибка оценки описания (слово '%s'): %s", word, e)
        return _offline_verdict(word, answer)
