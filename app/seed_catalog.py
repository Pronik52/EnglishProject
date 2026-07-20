"""Наполнение каталога слов из JSON-файла.

Запуск:
    python -m app.seed_catalog                      # data/catalog_seed.json
    python -m app.seed_catalog путь/к/файлу.json    # свой файл

Импорт идемпотентный: повторный запуск не создаёт дублей, а обновляет уже
существующие записи. Ключ записи — пара «слово + перевод» без учёта регистра,
поэтому book/книга и book/бронировать остаются двумя разными единицами.

Данные лежат в JSON, а не в коде: список слов — это контент, он должен
редактироваться без правки бизнес-логики.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from .database import SessionLocal
from . import models, schemas

DEFAULT_SEED = Path(__file__).resolve().parent.parent / "data" / "catalog_seed.json"

# Части речи, которые понимает приложение. Не ограничение базы, а проверка
# опечаток в файле: «nown» вместо «noun» иначе разошлось бы по каталогу.
_ALLOWED_POS = {"noun", "verb", "adjective", "adverb", "phrase", "preposition", "pronoun"}


class SeedError(Exception):
    """Ошибка в данных файла. Импорт прерывается до записи в базу."""


def _validate(data: dict) -> tuple[list, list]:
    """Проверяет структуру файла целиком ДО записи в базу.

    Валидируем всё сразу и падаем со списком проблем, а не на первой ошибке:
    так человек чинит файл за один заход, а не за десять запусков.
    """
    problems = []

    categories = data.get("categories") or []
    words = data.get("words") or []
    if not categories:
        problems.append("в файле нет ни одной категории")
    if not words:
        problems.append("в файле нет ни одного слова")

    slugs = set()
    for i, category in enumerate(categories):
        for field in ("slug", "title"):
            if not (category.get(field) or "").strip():
                problems.append(f"категория #{i}: пустое поле {field}")
        slug = (category.get("slug") or "").strip()
        if slug in slugs:
            problems.append(f"категория #{i}: slug «{slug}» повторяется")
        slugs.add(slug)

    seen_meanings = set()
    for i, word in enumerate(words):
        text = (word.get("text") or "").strip()
        translation = (word.get("translation") or "").strip()
        label = f"слово #{i} ({text or '?'})"

        if not text:
            problems.append(f"{label}: пустое поле text")
        if not translation:
            problems.append(f"{label}: пустое поле translation")

        level = (word.get("level") or "").strip().upper()
        if level not in schemas.LEVELS:
            problems.append(
                f"{label}: недопустимый уровень «{level}», ожидается один из "
                f"{', '.join(schemas.LEVELS)}"
            )

        pos = (word.get("part_of_speech") or "").strip().lower()
        if pos and pos not in _ALLOWED_POS:
            problems.append(f"{label}: неизвестная часть речи «{pos}»")

        word_categories = word.get("categories") or []
        if not word_categories:
            problems.append(f"{label}: не указана ни одна категория")
        for slug in word_categories:
            if slug not in slugs:
                problems.append(f"{label}: категория «{slug}» не описана в файле")

        key = (text.lower(), translation.lower())
        if key in seen_meanings:
            problems.append(f"{label}: пара «{text} / {translation}» повторяется в файле")
        seen_meanings.add(key)

    if problems:
        raise SeedError("Файл не прошёл проверку:\n  - " + "\n  - ".join(problems))

    return categories, words


def seed(db: Session, path: Path = DEFAULT_SEED) -> dict:
    """Загружает категории и слова. Возвращает отчёт о том, что изменилось."""
    if not path.exists():
        raise SeedError(f"Файл не найден: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SeedError(f"Файл не является корректным JSON: {e}") from e

    categories, words = _validate(data)

    report = {"categories_created": 0, "categories_updated": 0,
              "words_created": 0, "words_updated": 0}

    # --- Категории ---
    by_slug = {c.slug: c for c in db.query(models.Category).all()}
    for item in categories:
        slug = item["slug"].strip()
        existing = by_slug.get(slug)
        if existing is None:
            existing = models.Category(slug=slug)
            db.add(existing)
            by_slug[slug] = existing
            report["categories_created"] += 1
        else:
            report["categories_updated"] += 1
        existing.title = item["title"].strip()
        existing.sort_order = int(item.get("sort_order", 100))
        existing.is_active = bool(item.get("is_active", True))
    db.flush()

    # --- Слова ---
    # Существующие тянем одним запросом и сверяем в памяти: файл небольшой,
    # а запрос на каждое слово превратил бы импорт в сотни обращений к базе.
    existing_words = {
        (w.text.strip().lower(), w.translation.strip().lower()): w
        for w in db.query(models.CatalogWord).all()
    }

    for item in words:
        text = item["text"].strip()
        translation = item["translation"].strip()
        key = (text.lower(), translation.lower())

        word = existing_words.get(key)
        if word is None:
            word = models.CatalogWord(text=text, translation=translation)
            db.add(word)
            existing_words[key] = word
            report["words_created"] += 1
        else:
            report["words_updated"] += 1

        word.part_of_speech = (item.get("part_of_speech") or "").strip().lower() or None
        word.level = item["level"].strip().upper()
        word.transcription = (item.get("transcription") or "").strip() or None
        word.example_en = (item.get("example_en") or "").strip() or None
        word.example_ru = (item.get("example_ru") or "").strip() or None
        word.frequency_rank = int(item.get("frequency_rank", 1000))
        word.is_active = bool(item.get("is_active", True))
        word.categories = [by_slug[s] for s in item["categories"]]

    db.commit()
    return report


def main(argv: list) -> int:
    path = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_SEED
    db = SessionLocal()
    try:
        report = seed(db, path)
    except SeedError as e:
        print(f"Импорт не выполнен.\n{e}")
        return 1
    finally:
        db.close()

    print(f"Каталог загружен из {path}")
    print(f"  категории: создано {report['categories_created']}, "
          f"обновлено {report['categories_updated']}")
    print(f"  слова:     создано {report['words_created']}, "
          f"обновлено {report['words_updated']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
