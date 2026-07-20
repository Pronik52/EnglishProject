"""Каталог готовых слов: выдача с фильтрами и массовое добавление в словарь.

Каталог общий для всех, личный словарь — у каждого свой. Здесь живёт всё, что
связывает эти две сущности: пометка «уже добавлено» в выдаче и перенос
выбранных каталожных слов в таблицу words.

Два принципа, которых держится модуль:

1. Никаких N+1. Статус «уже в словаре» для целой страницы каталога считается
   двумя запросами, а не одним запросом на слово.
2. Серверу нельзя присылать перевод и прочие данные слова. Клиент передаёт
   только идентификаторы, всё остальное берётся из каталога — иначе через
   массовое добавление можно было бы записать в словарь что угодно.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from .. import models, schemas
from . import words as crud_words


# Человеческие подписи уровней для справочника.
_LEVEL_TITLES = {
    "A1": "A1 · начинающий",
    "A2": "A2 · базовый",
    "B1": "B1 · средний",
    "B2": "B2 · выше среднего",
    "C1": "C1 · продвинутый",
    "C2": "C2 · владение в совершенстве",
}


def list_levels() -> list[dict]:
    """Уровни, для которых наполнен каталог."""
    return [{"code": code, "title": _LEVEL_TITLES.get(code, code)}
            for code in schemas.CATALOG_LEVELS]


def list_categories(db: Session, level: str = None) -> list[dict]:
    """Активные категории. Если задан уровень — с числом слов на нём.

    Счётчик считается одним запросом с группировкой, а не выборкой на каждую
    категорию. Категории без слов на выбранном уровне остаются в списке с
    нулём: так пользователь видит, что тема есть, но пока пуста.
    """
    categories = db.query(models.Category).filter(
        models.Category.is_active == True
    ).order_by(models.Category.sort_order, models.Category.title).all()

    counts = {}
    query = (
        db.query(models.catalog_word_categories.c.category_id,
                 func.count(models.catalog_word_categories.c.catalog_word_id))
        .join(models.CatalogWord,
              models.CatalogWord.id == models.catalog_word_categories.c.catalog_word_id)
        .filter(models.CatalogWord.is_active == True)
    )
    if level:
        query = query.filter(models.CatalogWord.level == level)
    for category_id, count in query.group_by(models.catalog_word_categories.c.category_id):
        counts[category_id] = count

    return [{"id": c.id, "slug": c.slug, "title": c.title,
             "words_count": counts.get(c.id, 0)} for c in categories]


def _owned_keys(db: Session, owner_id: int, catalog_words: list) -> tuple[set, set]:
    """Что из переданных каталожных слов уже есть у пользователя.

    Возвращает два множества: идентификаторы каталожных записей и
    нормализованные пары (слово, перевод).

    Проверок именно две, потому что слово могло попасть в словарь двумя
    путями: из каталога (тогда есть catalog_word_id) или руками до появления
    каталога (тогда сверяем по тексту). Оба запроса — по одному на страницу.
    """
    if not catalog_words:
        return set(), set()

    ids = [w.id for w in catalog_words]
    by_id = {
        row[0] for row in
        db.query(models.Word.catalog_word_id).filter(
            models.Word.owner_id == owner_id,
            models.Word.catalog_word_id.in_(ids)
        ).all()
        if row[0] is not None
    }

    # Пары берём из слов пользователя одним запросом и сверяем в памяти:
    # словарь одного человека невелик, а SQL с составным IN по двум колонкам
    # не переносим между SQLite и PostgreSQL.
    pairs = {
        (text.strip().lower(), translation.strip().lower())
        for text, translation in
        db.query(models.Word.text, models.Word.translation).filter(
            models.Word.owner_id == owner_id
        ).all()
    }
    return by_id, pairs


def _is_owned(word, owned_ids: set, owned_pairs: set) -> bool:
    return (word.id in owned_ids
            or (word.text.strip().lower(), word.translation.strip().lower()) in owned_pairs)


def list_catalog_words(db: Session, owner_id: int, level: str = None,
                       category_slug: str = None, search: str = None,
                       hide_added: bool = False, skip: int = 0, limit: int = 50) -> dict:
    """Каталог с фильтрами, пагинацией и пометкой «уже в словаре».

    Сортировка: сначала частотность, затем алфавит. Приоритет «сначала ещё не
    добавленные» применяется уже к выбранной странице — иначе пришлось бы
    тащить личный словарь в SQL-сортировку и терять переносимость между
    SQLite и PostgreSQL.
    """
    query = db.query(models.CatalogWord).filter(models.CatalogWord.is_active == True)

    if level:
        query = query.filter(models.CatalogWord.level == level)

    if category_slug:
        query = (query
                 .join(models.catalog_word_categories,
                       models.catalog_word_categories.c.catalog_word_id == models.CatalogWord.id)
                 .join(models.Category,
                       models.Category.id == models.catalog_word_categories.c.category_id)
                 .filter(models.Category.slug == category_slug,
                         models.Category.is_active == True))

    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(models.CatalogWord.text.ilike(pattern) |
                             models.CatalogWord.translation.ilike(pattern))

    total = query.count()

    items = (query
             .options(selectinload(models.CatalogWord.categories))
             .order_by(models.CatalogWord.frequency_rank, models.CatalogWord.text)
             .offset(skip).limit(limit).all())

    owned_ids, owned_pairs = _owned_keys(db, owner_id, items)

    result = []
    for word in items:
        in_dictionary = _is_owned(word, owned_ids, owned_pairs)
        if hide_added and in_dictionary:
            continue
        result.append({
            "id": word.id,
            "text": word.text,
            "translation": word.translation,
            "part_of_speech": word.part_of_speech,
            "level": word.level,
            "transcription": word.transcription,
            "example_en": word.example_en,
            "example_ru": word.example_ru,
            "categories": [c.slug for c in word.categories],
            "in_dictionary": in_dictionary,
        })

    # Ещё не добавленные — выше: пользователь пришёл выбирать новое.
    result.sort(key=lambda w: w["in_dictionary"])
    return {"items": result, "total": total}


def add_words_to_dictionary(db: Session, owner_id: int, word_ids: list,
                            is_premium: bool = False) -> dict:
    """Массовое добавление каталожных слов в личный словарь.

    Операция идемпотентна: повторный запрос с теми же идентификаторами не
    создаёт дублей, а возвращает их как пропущенные. Гарантию даёт не только
    эта проверка, но и уникальный ключ в базе — от гонки одинаковых запросов
    код в одиночку не защищает.

    Дневной лимит бесплатного тарифа общий с ручным добавлением: если
    выбранное не помещается в остаток, добавляем сколько влезает, а остальное
    возвращаем отдельным списком — чтобы интерфейс мог предложить Premium.

    ИИ здесь не вызывается: учебной фразой становится курируемый пример из
    каталога. Картинка дорисуется лениво, при первом показе слова в режиме
    описания.
    """
    catalog_words = db.query(models.CatalogWord).filter(
        models.CatalogWord.id.in_(word_ids),
        models.CatalogWord.is_active == True
    ).all()
    found = {w.id: w for w in catalog_words}

    # Несуществующие и выключенные записи — это ошибка запроса, а не дубль.
    failed_ids = [wid for wid in word_ids if wid not in found]
    errors = []
    if failed_ids:
        errors.append(f"Слова не найдены в каталоге или отключены: {len(failed_ids)}")

    owned_ids, owned_pairs = _owned_keys(db, owner_id, catalog_words)

    # Остаток дневного лимита. Premium не ограничен.
    remaining = None
    if not is_premium:
        used = crud_words.count_words_created_today(db, owner_id)
        remaining = max(0, crud_words.FREE_DAILY_WORD_LIMIT - used)

    added_ids, skipped_ids, limit_skipped_ids = [], [], []

    # Порядок обхода — как прислал клиент: так предсказуемо, какие слова
    # попадут в остаток лимита, а какие нет.
    for wid in word_ids:
        word = found.get(wid)
        if word is None:
            continue

        if _is_owned(word, owned_ids, owned_pairs):
            skipped_ids.append(wid)
            continue

        if remaining is not None and len(added_ids) >= remaining:
            limit_skipped_ids.append(wid)
            continue

        db.add(_build_word(word, owner_id))
        added_ids.append(wid)
        # Дозаписываем в множества: если один и тот же id пришёл дважды
        # внутри запроса, второй раз он уже считается дублем.
        owned_ids.add(wid)
        owned_pairs.add((word.text.strip().lower(), word.translation.strip().lower()))

    if added_ids:
        db.commit()

    if limit_skipped_ids:
        errors.append(
            f"Дневной лимит бесплатного тарифа исчерпан "
            f"({crud_words.FREE_DAILY_WORD_LIMIT} слов в день), "
            f"не добавлено: {len(limit_skipped_ids)}. Оформите Premium для безлимита."
        )

    daily_remaining = -1
    if not is_premium:
        daily_remaining = max(
            0, crud_words.FREE_DAILY_WORD_LIMIT - crud_words.count_words_created_today(db, owner_id)
        )

    return {
        "added_count": len(added_ids),
        "skipped_count": len(skipped_ids),
        "limit_skipped_count": len(limit_skipped_ids),
        "failed_count": len(failed_ids),
        "added_ids": added_ids,
        "skipped_ids": skipped_ids,
        "limit_skipped_ids": limit_skipped_ids,
        "failed_ids": failed_ids,
        "errors": errors,
        "daily_remaining": daily_remaining,
    }


def _build_word(catalog_word: models.CatalogWord, owner_id: int) -> models.Word:
    """Запись личного словаря из каталожной.

    Прогресс начинается с нуля, как у слова, добавленного вручную: слово сразу
    «к повтору» и попадает в тот же механизм интервальных повторений.
    """
    from datetime import datetime

    return models.Word(
        text=catalog_word.text,
        translation=catalog_word.translation,
        # Курируемый пример становится учебной фразой. Если примера нет,
        # оставляем пусто — фразу можно будет сгенерировать кнопкой
        # «другая фраза», как для любого слова.
        phrase=catalog_word.example_en,
        phrase_ru=catalog_word.example_ru,
        catalog_word_id=catalog_word.id,
        srs_level=0,
        due_at=datetime.utcnow(),
        owner_id=owner_id,
    )
