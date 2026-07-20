"""Генерация английской фразы и её русского перевода через Groq API.

Это «онлайн»-путь генерации: ИИ придумывает короткую английскую фразу со
словом в нужном значении и сразу даёт её русский перевод. Модуль спроектирован
так, чтобы НИКОГДА не бросать исключение наружу — при любой проблеме
(нет ключа, нет сети, таймаут, кривой JSON) возвращается None, и вызывающий
слой (app/phrases.py) откатывается на детерминированный оффлайн-фолбэк.
"""

from __future__ import annotations

import os
import json
import random
import logging

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Модель Groq и таймаут запроса. Держим таймаут небольшим: если ИИ недоступен,
# лучше быстро уйти в фолбэк, чем заставлять пользователя ждать.
_MODEL = "llama-3.3-70b-versatile"
_TIMEOUT_SECONDS = 15.0


# Случайные бытовые контексты — подмешиваем один в промпт, чтобы при повторных
# генерациях модель каждый раз строила фразу в новой ситуации, а не выдавала
# один и тот же «шаблонный» ответ.
_SCENARIOS = [
    "everyday home life", "work or study", "travel and transport",
    "family and friends", "nature and weather", "food and cooking",
    "sport and hobbies", "city, shops and money", "health and body",
    "feelings and plans for the future",
]


def _build_prompt(word: str, translation: str, level: str, avoid: str = "") -> str:
    """Промпт, требующий строго JSON с английской фразой и её переводом.

    scenario и запрет на повтор `avoid` обеспечивают разнообразие при
    повторных нажатиях «другая фраза».
    """
    scenario = random.choice(_SCENARIOS)
    avoid_line = ""
    if avoid:
        avoid_line = (
            f"- must be clearly DIFFERENT from this phrase, not a paraphrase "
            f"of it: \"{avoid}\";\n"
        )
    return (
        f"You generate example phrases for an English vocabulary learner.\n"
        f"Word: \"{word}\"\n"
        f"Its intended Russian meaning: \"{translation}\"\n"
        f"Learner CEFR level: {level}\n\n"
        f"Produce ONE short English phrase that:\n"
        f"- uses the word \"{word}\" exactly in the meaning \"{translation}\";\n"
        f"- matches the difficulty of CEFR level {level};\n"
        f"- is set in the context of {scenario};\n"
        f"{avoid_line}"
        f"and its precise Russian translation.\n\n"
        f"Also describe the situation of the phrase as a picture: one English\n"
        f"sentence naming who is in the scene, what they are doing and where.\n"
        f"It must be concrete and drawable (no abstractions, no text in the\n"
        f"image) — it will be used as a prompt for an image model.\n\n"
        f"Respond with ONLY a JSON object, no explanations, in this exact shape:\n"
        f'{{"phrase_en": "...", "phrase_ru": "...", "scene_prompt": "..."}}'
    )


async def ai_generate_phrase(word: str, translation: str, level: str = "A1",
                             avoid: str = "") -> dict | None:
    """Одна английская фраза со словом + её русский перевод, через Groq.

    avoid — фраза, которую нужно НЕ повторять (для кнопки «другая фраза»).

    Возвращает {"phrase_en": str, "phrase_ru": str, "scene_prompt": str} при
    успехе, иначе None.
    Никогда не бросает исключение: любая ошибка логируется как warning → None.

    Особый случай: если ИИ вернул phrase_en, но phrase_ru или scene_prompt
    пустые/отсутствуют — это НЕ ошибка. Возвращаем "" (перевод дозаполнит слой
    выше, а описание сцены соберётся из самой фразы).
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY не задан — пропускаем ИИ-генерацию фразы.")
        return None

    try:
        # Импорт внутри функции: если библиотека groq не установлена,
        # приложение не должно падать при импорте модуля.
        from groq import AsyncGroq

        client = AsyncGroq(api_key=api_key, timeout=_TIMEOUT_SECONDS)
        resp = await client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": _build_prompt(word, translation, level, avoid)}],
            response_format={"type": "json_object"},
            # Высокая температура + случайный контекст в промпте → каждый раз
            # новая фраза при повторных нажатиях «другая фраза».
            temperature=1.1,
        )

        content = resp.choices[0].message.content if resp.choices else None
        if not content:
            logger.warning("Groq вернул пустой ответ для слова '%s'.", word)
            return None

        data = json.loads(content)
        phrase_en = (data.get("phrase_en") or "").strip()
        if not phrase_en:
            logger.warning("В ответе Groq нет поля phrase_en (слово '%s').", word)
            return None

        # phrase_ru и scene_prompt могут отсутствовать — это допустимо, вернём "".
        phrase_ru = (data.get("phrase_ru") or "").strip()
        scene_prompt = (data.get("scene_prompt") or "").strip()
        return {"phrase_en": phrase_en, "phrase_ru": phrase_ru, "scene_prompt": scene_prompt}

    except json.JSONDecodeError as e:
        logger.warning("Не удалось распарсить JSON от Groq (слово '%s'): %s", word, e)
        return None
    except Exception as e:
        # Таймаут, сетевая ошибка, ошибка API, отсутствие пакета groq и т.п.
        logger.warning("Ошибка ИИ-генерации фразы (слово '%s'): %s", word, e)
        return None
