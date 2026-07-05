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


# --- Шаблоны по уровню сложности и части речи. {w} — место для слова. ---
# Уровни CEFR сгруппированы в три набора: simple (A1/A2), medium (B1/B2),
# advanced (C1). Для A1 фразы максимально короткие и из простых слов.
_LEVEL_TIER = {"A1": "simple", "A2": "simple", "B1": "medium", "B2": "medium", "C1": "advanced"}

# Простой набор (A1/A2): короткие фразы из базовой лексики.
_SIMPLE = {
    "noun": [
        "I see a {w}.",
        "This is my {w}.",
        "I have a {w}.",
        "Look at the {w}!",
        "I like this {w}.",
        "It is a big {w}.",
    ],
    "verb": [
        "I like to {w}.",
        "Let's {w} now.",
        "I can {w}.",
        "We {w} every day.",
        "Do you {w}?",
        "I want to {w}.",
    ],
    "adj": [
        "It is the {w} one.",
        "I want the {w} one.",
        "The {w} one is here.",
        "Give me the {w} box.",
        "This is the {w} part.",
        "I like the {w} car.",
    ],
    "adv": [
        "He runs {w}.",
        "She sings {w}.",
        "Do it {w}.",
        "They walk {w}.",
        "We work {w}.",
        "I eat {w}.",
    ],
}

# Средний набор (B1/B2): обычные бытовые фразы.
_MEDIUM = {
    "noun": [
        "Can you pass me the {w}, please?",
        "I bought a new {w} yesterday.",
        "Where did you put the {w}?",
        "This {w} is exactly what I needed.",
        "She showed me her favourite {w}.",
        "We talked about the {w} for hours.",
        "He forgot his {w} at home.",
        "That {w} looks really expensive.",
    ],
    "verb": [
        "I want to {w} every day.",
        "They like to {w} together.",
        "Let's {w} before it gets dark.",
        "Do you know how to {w}?",
        "We should {w} more often.",
        "She taught me how to {w}.",
        "It's hard to {w} when you're tired.",
        "He promised to {w} tomorrow.",
    ],
    "adj": [
        "The {w} one is over there.",
        "She always picks the {w} option.",
        "I noticed the {w} part immediately.",
        "They chose the {w} route in the end.",
        "Everyone remembered the {w} scene.",
        "The {w} chapter was my favourite.",
        "I couldn't find the {w} page.",
        "He kept the {w} letter for years.",
    ],
    "adv": [
        "She finished the work {w}.",
        "He spoke to us very {w}.",
        "Please drive {w} on this road.",
        "They answered all the questions {w}.",
        "The team handled it {w}.",
        "You did that remarkably {w}.",
        "Everything went {w} in the end.",
        "He always explains things {w}.",
    ],
}

# Сложный набор (C1): длиннее, богаче лексика и структура.
_ADVANCED = {
    "noun": [
        "The committee spent weeks debating the future of the {w}.",
        "Her research shed new light on the origins of the {w}.",
        "Few people appreciate just how complex a {w} can be.",
        "The article examines the {w} from several angles.",
        "They reached no agreement about the {w} despite lengthy talks.",
        "The {w} proved far more significant than anyone had expected.",
    ],
    "verb": [
        "It would be unwise to {w} without weighing the consequences.",
        "They were reluctant to {w} until all the facts emerged.",
        "Under such circumstances, few would dare to {w}.",
        "The report urges policymakers to {w} without delay.",
        "She managed to {w} despite considerable opposition.",
        "There is little incentive to {w} in the current climate.",
    ],
    "adj": [
        "The committee eventually settled on the {w} option.",
        "Critics singled out the {w} scene for particular praise.",
        "Her analysis centred on the {w} case.",
        "The {w} proposal generated considerable debate.",
        "They dismissed the {w} approach without much discussion.",
        "The {w} chapter proved the most memorable.",
    ],
    "adv": [
        "The negotiations proceeded {w} despite the underlying tension.",
        "She responded {w}, choosing each word with care.",
        "The system handled the surge of requests {w}.",
        "He defended his thesis {w} before the committee.",
        "Events unfolded {w}, leaving little time to react.",
        "The team executed the plan {w} and without hesitation.",
    ],
}

_TIERS = {"simple": _SIMPLE, "medium": _MEDIUM, "advanced": _ADVANCED}


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


def generate_variants(word: str, translation: Optional[str] = None,
                      level: str = "A1", count: int = 3) -> List[str]:
    """Несколько разных фраз, подходящих слову по смыслу и уровню сложности.

    Детерминированный seed от слова и уровня: одно слово на одном уровне даёт
    стабильный набор фраз, но у разных слов/уровней наборы различаются.
    """
    tier = _LEVEL_TIER.get((level or "A1").upper(), "simple")
    pos = _classify(word, translation)
    templates = _TIERS[tier][pos]
    count = max(1, min(count, len(templates)))
    rnd = random.Random(f"{word.lower()}|{tier}")
    chosen = rnd.sample(templates, count)
    return [t.format(w=word.strip()) for t in chosen]


def generate_phrase(word: str, translation: Optional[str] = None, level: str = "A1") -> str:
    """Одна фраза, подходящая слову по смыслу и уровню сложности."""
    return generate_variants(word, translation, level=level, count=1)[0]
