"""Резервный перевод английской фразы на русский.

В стандартной библиотеке Python оффлайн-перевода нет — любой переводчик требует
внешнюю библиотеку и сеть. Используем deep-translator (Google) как онлайн-путь.
При любой ошибке (нет сети, недоступность сервиса, пустой ввод) возвращаем ""
и НИКОГДА не падаем — вызывающий слой сам решит, чем заполнить перевод.
"""

import logging

logger = logging.getLogger(__name__)


def translate_to_ru(text: str) -> str:
    """Переводит английский текст на русский. При ошибке возвращает ""."""
    text = (text or "").strip()
    if not text:
        return ""
    try:
        # Импорт внутри функции: отсутствие пакета не должно ронять приложение.
        from deep_translator import GoogleTranslator

        result = GoogleTranslator(source="en", target="ru").translate(text)
        return result or ""
    except Exception as e:
        logger.warning("Не удалось перевести фразу на русский: %s", e)
        return ""
