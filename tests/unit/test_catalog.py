"""Каталог готовых слов: фильтры, статус «уже в словаре», массовое добавление.

Отдельно проверяется, что появление каталога не сломало ручное добавление —
это было главным требованием к задаче.
"""

import json

import pytest

from app import models, schemas
from app.crud import catalog as crud_catalog
from app.crud.words import DAILY_WORD_LIMIT, create_word
from tests.conftest import run_async


# --- фикстуры каталога ---

@pytest.fixture
def catalog(db_session):
    """Небольшой каталог: две категории, слова разных уровней.

    Специально включает два значения слова book — на них проверяется, что
    каталог работает на уровне значения, а не строки.
    """
    food = models.Category(slug="food", title="Еда", sort_order=10)
    travel = models.Category(slug="travel", title="Путешествия", sort_order=20)
    hidden = models.Category(slug="hidden", title="Скрытая", sort_order=30, is_active=False)
    db_session.add_all([food, travel, hidden])
    db_session.flush()

    words = {
        "apple": models.CatalogWord(text="apple", translation="яблоко", level="A1",
                                    part_of_speech="noun", frequency_rank=1,
                                    example_en="I eat an apple.", example_ru="Я ем яблоко.",
                                    categories=[food]),
        "bread": models.CatalogWord(text="bread", translation="хлеб", level="A1",
                                    part_of_speech="noun", frequency_rank=2,
                                    example_en="Fresh bread smells good.",
                                    example_ru="Свежий хлеб вкусно пахнет.",
                                    categories=[food]),
        "recipe": models.CatalogWord(text="recipe", translation="рецепт", level="B1",
                                     part_of_speech="noun", frequency_rank=3,
                                     categories=[food]),
        "city": models.CatalogWord(text="city", translation="город", level="A1",
                                   part_of_speech="noun", frequency_rank=4,
                                   categories=[travel]),
        "book_n": models.CatalogWord(text="book", translation="книга", level="A1",
                                     part_of_speech="noun", frequency_rank=5,
                                     categories=[travel]),
        "book_v": models.CatalogWord(text="book", translation="бронировать", level="B1",
                                     part_of_speech="verb", frequency_rank=6,
                                     categories=[travel]),
        "off": models.CatalogWord(text="obsolete", translation="устаревшее", level="A1",
                                  frequency_rank=7, is_active=False, categories=[food]),
        "itinerary": models.CatalogWord(text="itinerary", translation="маршрут поездки",
                                        level="C1", part_of_speech="noun",
                                        frequency_rank=8, categories=[travel]),
    }
    db_session.add_all(words.values())
    db_session.commit()
    return words


def _headers(client, test_user):
    login = client.post("/api/v1/auth/token",
                        data={"username": test_user.email, "password": "secret"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# --- 1. категории ---

def test_categories_list_is_sorted_and_hides_inactive(db_session, catalog):
    result = crud_catalog.list_categories(db_session)
    slugs = [c["slug"] for c in result]
    assert slugs == ["food", "travel"]        # hidden не показывается
    assert result[0]["title"] == "Еда"


def test_categories_count_words_of_selected_level(db_session, catalog):
    result = {c["slug"]: c["words_count"] for c in crud_catalog.list_categories(db_session, level="A1")}
    # В «Еде» на A1 активны apple и bread; obsolete выключено и не считается.
    assert result["food"] == 2
    assert result["travel"] == 2              # city и book/книга


def test_levels_cover_catalog_range():
    codes = [lvl["code"] for lvl in crud_catalog.list_levels()]
    assert codes == ["A1", "A2", "B1", "B2", "C1", "C2"]


# --- 2-3. фильтрация ---

def test_filter_by_level(db_session, test_user, catalog):
    result = crud_catalog.list_catalog_words(db_session, owner_id=test_user.id, level="A1")
    texts = sorted(w["text"] for w in result["items"])
    assert texts == ["apple", "book", "bread", "city"]
    assert result["total"] == 4


def test_filter_by_category(db_session, test_user, catalog):
    result = crud_catalog.list_catalog_words(
        db_session, owner_id=test_user.id, level="A1", category_slug="food")
    assert sorted(w["text"] for w in result["items"]) == ["apple", "bread"]


def test_inactive_words_are_never_returned(db_session, test_user, catalog):
    result = crud_catalog.list_catalog_words(db_session, owner_id=test_user.id, level="A1")
    assert "obsolete" not in [w["text"] for w in result["items"]]


def test_search_matches_english_and_russian(db_session, test_user, catalog):
    by_en = crud_catalog.list_catalog_words(db_session, owner_id=test_user.id,
                                            level="A1", search="app")
    assert [w["text"] for w in by_en["items"]] == ["apple"]

    by_ru = crud_catalog.list_catalog_words(db_session, owner_id=test_user.id,
                                            level="A1", search="хлеб")
    assert [w["text"] for w in by_ru["items"]] == ["bread"]


def test_pagination_reports_total_and_pages(client, db_session, test_user, catalog):
    resp = client.get("/api/v1/catalog/words?level=A1&limit=2&skip=0",
                      headers=_headers(client, test_user))
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 4
    assert data["pages"] == 2
    assert data["page"] == 0


# --- 4. статус «уже в словаре» ---

def test_word_added_from_catalog_is_marked(db_session, test_user, catalog):
    crud_catalog.add_words_to_dictionary(
        db_session, owner_id=test_user.id, word_ids=[catalog["apple"].id], is_premium=True)

    result = crud_catalog.list_catalog_words(db_session, owner_id=test_user.id, level="A1")
    flags = {w["text"]: w["in_dictionary"] for w in result["items"]}
    assert flags["apple"] is True
    assert flags["bread"] is False


def test_manually_added_word_is_also_marked(db_session, test_user, catalog):
    """Слово, заведённое руками ещё до каталога, тоже должно определяться —
    иначе пользователь добавит его вторично и получит дубль."""
    run_async(create_word(
        db_session, schemas.WordCreate(text="Apple", translation="Яблоко"), test_user.id))

    result = crud_catalog.list_catalog_words(db_session, owner_id=test_user.id, level="A1")
    flags = {w["text"]: w["in_dictionary"] for w in result["items"]}
    assert flags["apple"] is True             # сверка без учёта регистра


def test_other_meaning_of_same_word_is_not_marked(db_session, test_user, catalog):
    """book/книга в словаре не должно закрывать book/бронировать:
    это разные учебные единицы."""
    crud_catalog.add_words_to_dictionary(
        db_session, owner_id=test_user.id, word_ids=[catalog["book_n"].id], is_premium=True)

    b1 = crud_catalog.list_catalog_words(db_session, owner_id=test_user.id, level="B1")
    flags = {(w["text"], w["translation"]): w["in_dictionary"] for w in b1["items"]}
    assert flags[("book", "бронировать")] is False


def test_hide_added_filter(db_session, test_user, catalog):
    crud_catalog.add_words_to_dictionary(
        db_session, owner_id=test_user.id, word_ids=[catalog["apple"].id], is_premium=True)

    result = crud_catalog.list_catalog_words(
        db_session, owner_id=test_user.id, level="A1", hide_added=True)
    assert "apple" not in [w["text"] for w in result["items"]]


def test_not_added_words_come_first(db_session, test_user, catalog):
    crud_catalog.add_words_to_dictionary(
        db_session, owner_id=test_user.id, word_ids=[catalog["apple"].id], is_premium=True)

    result = crud_catalog.list_catalog_words(db_session, owner_id=test_user.id, level="A1")
    assert result["items"][-1]["text"] == "apple"


def test_other_users_dictionary_does_not_affect_status(db_session, test_user, catalog):
    stranger = models.User(email="stranger@example.com", hashed_password="x")
    db_session.add(stranger)
    db_session.commit()
    crud_catalog.add_words_to_dictionary(
        db_session, owner_id=stranger.id, word_ids=[catalog["apple"].id], is_premium=True)

    result = crud_catalog.list_catalog_words(db_session, owner_id=test_user.id, level="A1")
    flags = {w["text"]: w["in_dictionary"] for w in result["items"]}
    assert flags["apple"] is False


# --- 5. массовое добавление ---

def test_bulk_add_creates_words_with_curated_phrase(db_session, test_user, catalog):
    result = crud_catalog.add_words_to_dictionary(
        db_session, owner_id=test_user.id,
        word_ids=[catalog["apple"].id, catalog["bread"].id], is_premium=True)

    assert result["added_count"] == 2
    assert result["skipped_count"] == 0

    word = db_session.query(models.Word).filter_by(text="apple").one()
    # Фраза берётся из каталога, а не генерируется ИИ.
    assert word.phrase == "I eat an apple."
    assert word.phrase_ru == "Я ем яблоко."
    assert word.catalog_word_id == catalog["apple"].id


def test_bulk_added_word_joins_normal_learning_flow(db_session, test_user, catalog):
    """Слово из каталога должно попадать в тот же механизм повторений."""
    crud_catalog.add_words_to_dictionary(
        db_session, owner_id=test_user.id, word_ids=[catalog["apple"].id], is_premium=True)

    word = db_session.query(models.Word).filter_by(text="apple").one()
    assert word.srs_level == 0
    assert word.is_learned is False
    assert word.due_at is not None            # сразу «к повтору»

    from app.crud.words import answer_word
    updated = answer_word(db_session, word.id, test_user.id, correct=True)
    assert updated.srs_level == 1


# --- 6-7. дубли и идемпотентность ---

def test_duplicates_are_skipped_not_created(db_session, test_user, catalog):
    ids = [catalog["apple"].id, catalog["bread"].id]
    crud_catalog.add_words_to_dictionary(db_session, test_user.id, ids, is_premium=True)
    again = crud_catalog.add_words_to_dictionary(db_session, test_user.id, ids, is_premium=True)

    assert again["added_count"] == 0
    assert again["skipped_count"] == 2
    assert sorted(again["skipped_ids"]) == sorted(ids)
    assert db_session.query(models.Word).filter_by(owner_id=test_user.id).count() == 2


def test_repeated_ids_inside_one_request_add_once(db_session, test_user, catalog):
    result = crud_catalog.add_words_to_dictionary(
        db_session, test_user.id,
        [catalog["apple"].id, catalog["apple"].id, catalog["apple"].id], is_premium=True)
    assert result["added_count"] == 1
    assert db_session.query(models.Word).filter_by(text="apple").count() == 1


def test_manually_added_word_blocks_catalog_duplicate(db_session, test_user, catalog):
    run_async(create_word(
        db_session, schemas.WordCreate(text="apple", translation="яблоко"), test_user.id))

    result = crud_catalog.add_words_to_dictionary(
        db_session, test_user.id, [catalog["apple"].id], is_premium=True)
    assert result["added_count"] == 0
    assert result["skipped_count"] == 1


def test_database_rejects_duplicate_even_past_the_code(db_session, test_user):
    """Последний рубеж — уникальный ключ в базе. Он защищает от гонки, когда
    два одинаковых запроса прошли проверку одновременно.

    Регистр меняем в английском слове: lower() в SQLite обрабатывает только
    латиницу, поэтому кириллический регистр на этом движке ключ не ловит.
    На PostgreSQL, где работает боевая база, lower() понимает и кириллицу.
    """
    from sqlalchemy.exc import IntegrityError

    db_session.add(models.Word(text="apple", translation="яблоко", owner_id=test_user.id))
    db_session.commit()

    db_session.add(models.Word(text="Apple", translation="яблоко", owner_id=test_user.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_check_handles_cyrillic_case(db_session, test_user):
    """Сверка перевода идёт в Python, поэтому «Яблоко» и «яблоко» считаются
    одним значением независимо от возможностей lower() у движка базы."""
    db_session.add(models.Word(text="apple", translation="Яблоко", owner_id=test_user.id))
    db_session.commit()

    from app.crud.words import find_duplicate
    assert find_duplicate(db_session, test_user.id, "apple", "яблоко") is not None
    assert find_duplicate(db_session, test_user.id, "apple", "фрукт") is None


def test_same_word_different_meaning_is_allowed(db_session, test_user):
    db_session.add(models.Word(text="book", translation="книга", owner_id=test_user.id))
    db_session.commit()
    db_session.add(models.Word(text="book", translation="бронировать", owner_id=test_user.id))
    db_session.commit()   # не должно упасть
    assert db_session.query(models.Word).filter_by(text="book").count() == 2


# --- 9. валидация входных данных ---

def test_unknown_ids_are_reported_as_failed(db_session, test_user, catalog):
    result = crud_catalog.add_words_to_dictionary(
        db_session, test_user.id, [catalog["apple"].id, 999999], is_premium=True)
    assert result["added_count"] == 1
    assert result["failed_count"] == 1
    assert result["failed_ids"] == [999999]
    assert result["errors"]


def test_inactive_catalog_word_cannot_be_added(db_session, test_user, catalog):
    result = crud_catalog.add_words_to_dictionary(
        db_session, test_user.id, [catalog["off"].id], is_premium=True)
    assert result["added_count"] == 0
    assert result["failed_count"] == 1


def test_empty_selection_is_rejected(client, test_user, catalog):
    resp = client.post("/api/v1/catalog/words/add", json={"word_ids": []},
                       headers=_headers(client, test_user))
    assert resp.status_code == 422


def test_batch_size_is_limited(client, test_user, catalog):
    resp = client.post("/api/v1/catalog/words/add",
                       json={"word_ids": list(range(schemas.MAX_BULK_ADD + 1))},
                       headers=_headers(client, test_user))
    assert resp.status_code == 422


def test_invalid_level_is_rejected(client, test_user, catalog):
    resp = client.get("/api/v1/catalog/words?level=Z9", headers=_headers(client, test_user))
    assert resp.status_code == 422


# --- 8. авторизация ---

@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/catalog/levels"),
    ("get", "/api/v1/catalog/categories"),
    ("get", "/api/v1/catalog/words"),
    ("post", "/api/v1/catalog/words/add"),
])
def test_catalog_requires_authentication(client, method, path):
    resp = getattr(client, method)(path) if method == "get" else client.post(path, json={"word_ids": [1]})
    assert resp.status_code == 401


def test_user_id_is_taken_from_token_not_from_body(client, db_session, test_user, catalog):
    """Даже если клиент пришлёт чужой owner_id, слово уйдёт текущему пользователю."""
    stranger = models.User(email="stranger@example.com", hashed_password="x")
    db_session.add(stranger)
    db_session.commit()

    client.post("/api/v1/catalog/words/add",
                json={"word_ids": [catalog["apple"].id], "owner_id": stranger.id},
                headers=_headers(client, test_user))

    assert db_session.query(models.Word).filter_by(owner_id=test_user.id).count() == 1
    assert db_session.query(models.Word).filter_by(owner_id=stranger.id).count() == 0


# --- дневной лимит (общий с ручным добавлением) ---

def test_bulk_add_respects_daily_limit(db_session, test_user, catalog):
    words = [models.CatalogWord(text=f"w{i}", translation=f"с{i}", level="A1",
                                frequency_rank=i) for i in range(DAILY_WORD_LIMIT + 3)]
    db_session.add_all(words)
    db_session.commit()

    result = crud_catalog.add_words_to_dictionary(
        db_session, test_user.id, [w.id for w in words], is_premium=False)

    assert result["added_count"] == DAILY_WORD_LIMIT
    assert result["limit_skipped_count"] == 3
    assert result["daily_remaining"] == 0
    # Пользователю объясняем, сколько слов не поместилось и что будет дальше.
    # Рекламы Premium здесь быть не должно: лимит — защита от злоупотреблений,
    # а не платная стена.
    message = " ".join(result["errors"])
    assert "3" in message and "завтра" in message
    assert "Premium" not in message


def test_limit_counter_is_shared_with_manual_adding(db_session, test_user, catalog):
    """Лимит один на оба способа: ручное добавление уменьшает остаток каталога."""
    run_async(create_word(
        db_session, schemas.WordCreate(text="manual", translation="ручное"), test_user.id))

    words = [models.CatalogWord(text=f"w{i}", translation=f"с{i}", level="A1")
             for i in range(DAILY_WORD_LIMIT)]
    db_session.add_all(words)
    db_session.commit()

    result = crud_catalog.add_words_to_dictionary(
        db_session, test_user.id, [w.id for w in words], is_premium=False)
    assert result["added_count"] == DAILY_WORD_LIMIT - 1
    assert result["limit_skipped_count"] == 1


def test_premium_has_no_daily_limit(db_session, test_user, catalog):
    words = [models.CatalogWord(text=f"w{i}", translation=f"с{i}", level="A1")
             for i in range(DAILY_WORD_LIMIT + 5)]
    db_session.add_all(words)
    db_session.commit()

    result = crud_catalog.add_words_to_dictionary(
        db_session, test_user.id, [w.id for w in words], is_premium=True)
    assert result["added_count"] == DAILY_WORD_LIMIT + 5
    assert result["daily_remaining"] == -1


# --- 10. ручное добавление не сломалось ---

def test_manual_adding_still_works(client, test_user, catalog):
    resp = client.post("/api/v1/words",
                       json={"text": "manual", "translation": "вручную"},
                       headers=_headers(client, test_user))
    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "manual"
    assert data["translation"] == "вручную"


def test_manual_adding_rejects_exact_duplicate(client, test_user, catalog):
    """Новое поведение: полный дубль теперь не создаётся. Раньше ограничения
    не было вовсе, и одно и то же слово можно было завести дважды."""
    headers = _headers(client, test_user)
    first = client.post("/api/v1/words", json={"text": "apple", "translation": "яблоко"},
                        headers=headers)
    assert first.status_code == 200

    second = client.post("/api/v1/words", json={"text": "apple", "translation": "яблоко"},
                         headers=headers)
    assert second.status_code == 409


def test_manual_adding_allows_second_meaning(client, test_user, catalog):
    headers = _headers(client, test_user)
    assert client.post("/api/v1/words", json={"text": "book", "translation": "книга"},
                       headers=headers).status_code == 200
    assert client.post("/api/v1/words", json={"text": "book", "translation": "бронировать"},
                       headers=headers).status_code == 200


# --- уровень пользователя ---

def test_catalog_uses_profile_level_by_default(client, db_session, test_user, catalog):
    test_user.level = "B1"
    db_session.commit()

    resp = client.get("/api/v1/catalog/words", headers=_headers(client, test_user))
    levels = {w["level"] for w in resp.json()["items"]}
    assert levels == {"B1"}


def test_advanced_profile_level_gets_its_own_words(client, db_session, test_user, catalog):
    """Каталог наполнен до C2, поэтому продвинутый профиль получает свой уровень,
    а не откат на B2."""
    test_user.level = "C1"
    db_session.commit()

    resp = client.get("/api/v1/catalog/words", headers=_headers(client, test_user))
    assert resp.status_code == 200
    assert {w["level"] for w in resp.json()["items"]} == {"C1"}


def test_profile_level_outside_catalog_falls_back(client, db_session, test_user, catalog,
                                                  monkeypatch):
    """Если каталог для уровня из профиля не наполнен, выдача не должна
    оказаться пустой без объяснения — показываем старший наполненный уровень.

    CATALOG_LEVELS подменяется: сам разрыв между шкалой профиля и наполненностью
    каталога временный, а поведение при нём проверять надо всегда."""
    monkeypatch.setattr(schemas, "CATALOG_LEVELS", ("A1", "A2", "B1"))
    test_user.level = "C1"
    db_session.commit()

    resp = client.get("/api/v1/catalog/words", headers=_headers(client, test_user))
    assert resp.status_code == 200
    assert {w["level"] for w in resp.json()["items"]} <= {"B1"}


def test_filter_does_not_change_profile_level(client, db_session, test_user, catalog):
    test_user.level = "A1"
    db_session.commit()

    client.get("/api/v1/catalog/words?level=B1", headers=_headers(client, test_user))
    db_session.refresh(test_user)
    assert test_user.level == "A1"


# --- производительность ---

def test_no_n_plus_one_queries(db_session, test_user, catalog):
    """Число SELECT'ов не должно расти вместе с числом слов: проверка наличия
    в словаре делается пачкой, а не запросом на каждое слово."""
    from sqlalchemy import event

    words = [models.CatalogWord(text=f"perf{i}", translation=f"тест{i}", level="A1",
                                frequency_rank=i) for i in range(40)]
    db_session.add_all(words)
    db_session.commit()
    ids = [w.id for w in words]

    selects = []
    engine = db_session.get_bind()

    def count(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        crud_catalog.add_words_to_dictionary(db_session, test_user.id, ids[:10], is_premium=True)
        few = len(selects)

        selects.clear()
        crud_catalog.add_words_to_dictionary(db_session, test_user.id, ids[10:], is_premium=True)
        many = len(selects)

        selects.clear()
        crud_catalog.list_catalog_words(db_session, owner_id=test_user.id, level="A1", limit=50)
        listing = len(selects)
    finally:
        event.remove(engine, "before_cursor_execute", count)

    # 10 слов и 30 слов должны стоить одинакового числа выборок.
    assert few == many, f"добавление масштабируется по SELECT: {few} против {many}"
    assert few <= 5
    assert listing <= 8, f"выдача делает {listing} выборок"


# --- наполнение каталога ---

def test_seed_validates_level(tmp_path, db_session):
    from app.seed_catalog import SeedError, seed

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "categories": [{"slug": "food", "title": "Еда"}],
        "words": [{"text": "apple", "translation": "яблоко", "level": "X9",
                   "categories": ["food"]}],
    }), encoding="utf-8")

    with pytest.raises(SeedError, match="уровень"):
        seed(db_session, bad)


def test_seed_validates_unknown_category(tmp_path, db_session):
    from app.seed_catalog import SeedError, seed

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "categories": [{"slug": "food", "title": "Еда"}],
        "words": [{"text": "apple", "translation": "яблоко", "level": "A1",
                   "categories": ["space"]}],
    }), encoding="utf-8")

    with pytest.raises(SeedError, match="категория"):
        seed(db_session, bad)


def test_seed_is_idempotent(tmp_path, db_session):
    from app.seed_catalog import seed

    good = tmp_path / "good.json"
    good.write_text(json.dumps({
        "categories": [{"slug": "food", "title": "Еда", "sort_order": 1}],
        "words": [{"text": "apple", "translation": "яблоко", "level": "A1",
                   "part_of_speech": "noun", "categories": ["food"]}],
    }), encoding="utf-8")

    first = seed(db_session, good)
    assert first["words_created"] == 1

    second = seed(db_session, good)
    assert second["words_created"] == 0
    assert second["words_updated"] == 1
    assert db_session.query(models.CatalogWord).count() == 1
