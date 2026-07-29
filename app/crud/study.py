"""Сборка учебной сессии: что повторять сегодня и каким режимом.

Логика живёт на сервере, а не в клиенте, намеренно. Раньше её целиком делал
frontend/js/study.js: грузил весь словарь и сортировал в JS. Под iOS это
пришлось бы написать второй раз и потом синхронно править в двух местах, а
любое расхождение выглядело бы как «на телефоне повторы другие». Теперь оба
клиента получают готовый список карточек и только рисуют их.
"""

from __future__ import annotations

import random
from typing import List, Optional

from sqlalchemy.orm import Session

from .. import models
from .words import due_filter

# Сколько карточек в сессии по умолчанию и максимум.
# 15 — это примерно 5-7 минут занятия: сессия должна заканчиваться, пока
# человек ещё не устал, иначе он бросает её на середине и теряет прогресс.
SESSION_DEFAULT_SIZE = 15
SESSION_MAX_SIZE = 50

# Режимы карточки.
MODE_CHOICE = "choice"      # узнавание: выбрать слово из вариантов
MODE_TYPE = "type"          # припоминание: вписать слово
MODE_DESCRIBE = "describe"  # продуктивное употребление: описать сцену

# Сколько вариантов показываем в режиме выбора (1 верный + 3 отвлекателя).
OPTIONS_COUNT = 4


def _pick_mode(word: models.Word) -> str:
    """Режим карточки по уровню SRS — лестница сложности.

    Смысл в том, что одно и то же слово по мере запоминания требует всё более
    сложного действия: сначала узнать среди четырёх, потом вспомнить и написать,
    и только на закрепляющих повторах — употребить в собственной фразе.

    До этого режим выбирался глобальным селектором со значением describe по
    умолчанию, то есть первая же карточка новичка просила написать текст на
    английском. Это и было главным барьером входа.
    """
    level = word.srs_level or 0
    if level <= 1:
        return MODE_CHOICE
    if level <= 3:
        return MODE_TYPE
    return MODE_DESCRIBE


def _scene_ready(word: models.Word) -> bool:
    """Есть ли картинка, которую можно описывать (или она вот-вот будет)."""
    return bool(word.image_url) or word.image_status == "pending"


def _distractor_pool(db: Session, owner_id: int, level: str,
                     need: int) -> List[str]:
    """Слова-отвлекатели для режима выбора.

    Собирается ОДИН раз на всю сессию, а не на карточку: иначе получаем N+1
    запрос на ровном месте. Сначала берём слова самого пользователя — они
    выглядят правдоподобнее всего, потому что человек их узнаёт, — и добираем
    каталогом того же уровня, если своих не хватает.

    Слова текущей сессии из пула НЕ вычитаем: у новичка их всего десяток, и
    после вычитания собственных отвлекателей не осталось бы вовсе. Правильный
    ответ каждой карточки отсекается персонально в _options_for.
    """
    pool: List[str] = []
    seen = set()

    own = db.query(models.Word.text).filter(
        models.Word.owner_id == owner_id
    ).limit(200).all()
    for (text,) in own:
        key = (text or "").strip().lower()
        if key and key not in seen:
            pool.append(text)
            seen.add(key)

    if len(pool) < need:
        catalog = db.query(models.CatalogWord.text).filter(
            models.CatalogWord.level == level,
            models.CatalogWord.is_active == True,  # noqa: E712
        ).order_by(models.CatalogWord.frequency_rank).limit(100).all()
        for (text,) in catalog:
            key = (text or "").strip().lower()
            if key and key not in seen:
                pool.append(text)
                seen.add(key)

    return pool


def _options_for(word: models.Word, pool: List[str]) -> Optional[List[str]]:
    """Перемешанные варианты ответа или None, если отвлекателей не хватило.

    None — не ошибка, а сигнал вызывающему коду понизить режим до ввода:
    викторина из двух вариантов подсказывает ответ, и лучше попросить вписать
    слово, чем показать выбор, который решается угадыванием.
    """
    target_key = (word.text or "").strip().lower()
    candidates = [t for t in pool if (t or "").strip().lower() != target_key]
    need = OPTIONS_COUNT - 1
    if len(candidates) < need:
        return None
    options = random.sample(candidates, need) + [word.text]
    random.shuffle(options)
    return options


def count_due(db: Session, owner_id: int) -> int:
    """Сколько слов пользователя ждут повторения прямо сейчас."""
    return db.query(models.Word).filter(
        models.Word.owner_id == owner_id,
        *due_filter()
    ).count()


def build_session(db: Session, owner_id: int, size: int = SESSION_DEFAULT_SIZE,
                  ahead: bool = False, level: str = "A1") -> dict:
    """Готовая сессия: список карточек с назначенными режимами.

    ahead=False — только то, что реально пора повторить. Пустой список здесь
    нормальный ответ: «на сегодня всё» — это часть интервальных повторов, а не
    ошибка, и клиент показывает именно такой экран.

    ahead=True — занятие сверх плана: берём невыученные слова независимо от
    срока, ближайшие к повтору первыми. Выученные не подмешиваем и здесь: если
    весь словарь пройден, честнее сказать об этом, чем гонять по кругу.
    """
    size = max(1, min(size, SESSION_MAX_SIZE))

    query = db.query(models.Word).filter(models.Word.owner_id == owner_id)
    if ahead:
        query = query.filter(models.Word.is_learned == False)  # noqa: E712
    else:
        query = query.filter(*due_filter())

    words = query.order_by(
        models.Word.due_at.asc(),
        models.Word.srs_level.asc(),
        models.Word.id.asc(),
    ).limit(size).all()

    cards = []
    if words:
        # need = OPTIONS_COUNT, а не OPTIONS_COUNT - 1: одним из слов пула
        # может оказаться сам правильный ответ, и его отсечёт _options_for.
        pool = _distractor_pool(db, owner_id, level, need=OPTIONS_COUNT)

        for word in words:
            mode = _pick_mode(word)
            # Варианты считаем всегда, когда они вообще собираются, а не только
            # для режима choice: пользователь может вручную переключить режим на
            # карточке, и без готовых вариантов такое переключение не сработало
            # бы — клиенту собирать их больше не из чего.
            options = _options_for(word, pool)

            if mode == MODE_DESCRIBE and not _scene_ready(word):
                # Описывать нечего — картинка не сгенерировалась или выключена.
                # Понижаем до ввода вместо тупикового экрана «картинки нет».
                mode = MODE_TYPE

            if mode == MODE_CHOICE and options is None:
                # Отвлекателей не набралось (пустой каталог и почти пустой
                # словарь) — просим вписать слово вместо выбора из двух.
                mode = MODE_TYPE

            cards.append({"word": word, "mode": mode, "options": options})

    return {
        "cards": cards,
        "due_total": count_due(db, owner_id),
        "ahead": ahead,
    }
