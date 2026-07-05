"""Генерация коротких фраз для запоминания слов — офлайн, без внешних API.

Идея: пользователь запоминает слово внутри короткой осмысленной фразы.
Чтобы фраза подходила слову по смыслу, сначала определяем его часть речи
(существительное / глагол / прилагательное / наречие), а затем подставляем
слово в шаблон, грамматически подходящий именно этой части речи.

Часть речи определяется по двум сигналам:
  1. Русский перевод — окончания русских слов надёжно кодируют часть речи
     (глаголы на -ть/-ться, прилагательные на -ый/-ая/-ое и т.д.).
  2. Английские суффиксы слова — как дополнительный/резервный признак.
"""

import re
import random
from typing import List, Optional


# --- Шаблоны по частям речи. {w} — место для слова. ---
# Существительное — слово обозначает предмет.
_NOUN = [
    "Can you pass me the {w}, please?",
    "I bought a new {w} yesterday.",
    "Where did you put the {w}?",
    "This {w} is exactly what I needed.",
    "She showed me her favourite {w}.",
    "We talked about the {w} for hours.",
    "He forgot his {w} at home.",
    "That {w} looks really expensive.",
]

# Глагол — слово обозначает действие (берём базовую форму: to {w}).
_VERB = [
    "I want to {w} every day.",
    "They like to {w} together.",
    "Let's {w} before it gets dark.",
    "Do you know how to {w}?",
    "We should {w} more often.",
    "She taught me how to {w}.",
    "It's hard to {w} when you're tired.",
    "He promised to {w} tomorrow.",
]

# Прилагательное — слово описывает признак.
_ADJ = [
    "The weather is very {w} today.",
    "That was a really {w} movie.",
    "This is such a {w} idea.",
    "He seems quite {w} lately.",
    "Everyone said the food was {w}.",
    "Her new house is surprisingly {w}.",
    "I've never met anyone so {w}.",
    "The results were more {w} than expected.",
]

# Наречие — слово описывает, как совершается действие.
_ADV = [
    "She finished the work {w}.",
    "He spoke to us very {w}.",
    "Please drive {w} on this road.",
    "They answered all the questions {w}.",
    "The team handled it {w}.",
    "You did that remarkably {w}.",
    "Everything went {w} in the end.",
    "He always explains things {w}.",
]

_TEMPLATES = {"noun": _NOUN, "verb": _VERB, "adj": _ADJ, "adv": _ADV}


def _first_ru_word(translation: str) -> str:
    """Берёт первое русское слово перевода (переводы бывают через запятую)."""
    parts = re.split(r"[,;/()]|\s+", translation.strip().lower())
    for p in parts:
        p = p.strip()
        # Пропускаем служебные частицы вроде "to", "быть".
        if p and p not in ("to", "the", "a", "an"):
            return p
    return translation.strip().lower()


def _pos_from_russian(translation: Optional[str]) -> Optional[str]:
    """Определяет часть речи по окончанию русского перевода."""
    if not translation:
        return None
    t = _first_ru_word(translation)

    # Глаголы: -ть, -ться, -тись, -чь (учить, учиться, беречь).
    if t.endswith(("ться", "тись")) or t.endswith("ть") or t.endswith("чь"):
        return "verb"
    # Прилагательные: словарная форма — мужской род единственного числа.
    # Намеренно НЕ берём -ые/-ие (мн. ч.) и -о: они путаются с
    # существительными (решение, окно). Наречия ловим по английскому -ly.
    if t.endswith(("ый", "ий", "ой", "ая", "яя", "ое", "ее")):
        return "adj"
    return None  # по умолчанию — существительное (см. _classify)


def _pos_from_english(word: str) -> Optional[str]:
    """Резервное определение части речи по английским суффиксам."""
    w = word.strip().lower()
    if w.endswith("ly"):
        return "adv"
    # Существительные проверяем раньше прилагательных: -ment (movement)
    # оканчивается на -ent, иначе его перехватит прилагательное.
    if w.endswith(("tion", "sion", "ment", "ness", "ity", "ship", "ism", "ance", "ence")):
        return "noun"
    if w.endswith(("ous", "ful", "ive", "able", "ible", "less", "ical", "ent", "ant")):
        return "adj"
    if w.endswith(("ing", "ate", "ise", "ize", "ify")):
        return "verb"
    return None


def _classify(word: str, translation: Optional[str]) -> str:
    """Итоговая часть речи: русский сигнал приоритетнее, затем английский."""
    return (
        _pos_from_russian(translation)
        or _pos_from_english(word)
        or "noun"
    )


def generate_variants(word: str, translation: Optional[str] = None, count: int = 3) -> List[str]:
    """Несколько разных фраз, подходящих слову по смыслу.

    Детерминированный seed от слова: одно слово даёт стабильный набор фраз,
    но у разных слов наборы различаются.
    """
    pos = _classify(word, translation)
    templates = _TEMPLATES[pos]
    count = max(1, min(count, len(templates)))
    rnd = random.Random(word.lower())
    chosen = rnd.sample(templates, count)
    return [t.format(w=word.strip()) for t in chosen]


def generate_phrase(word: str, translation: Optional[str] = None) -> str:
    """Одна короткая фраза, подходящая слову по смыслу."""
    return generate_variants(word, translation, count=1)[0]
