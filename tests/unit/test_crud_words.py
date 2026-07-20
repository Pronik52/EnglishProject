import pytest
from app.crud.words import (
    create_word, get_word, get_words_by_owner, delete_word,
    review_word, toggle_learned, get_random_unlearned_word,
    get_words_stats, SRS_MAX_LEVEL
)
from app import schemas
from tests.conftest import run_async

def test_create_word(db_session, test_user):
    word_data = schemas.WordCreate(text="test", translation="тест")
    word = run_async(create_word(db_session, word_data, test_user.id))

    assert word.text == "test"
    assert word.translation == "тест"
    assert word.owner_id == test_user.id
    assert word.is_learned == False
    assert word.review_count == 0

def test_get_word(db_session, test_word):
    retrieved_word = get_word(db_session, test_word.id, test_word.owner_id)
    assert retrieved_word is not None
    assert retrieved_word.id == test_word.id
    assert retrieved_word.text == test_word.text

def test_get_word_not_found(db_session, test_user):
    retrieved_word = get_word(db_session, 999, test_user.id)
    assert retrieved_word is None

def test_get_word_wrong_owner(db_session, test_word):
    # Создаем второго пользователя
    from app import models
    user2 = models.User(
        email="test2@example.com",
        hashed_password="$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"
    )
    db_session.add(user2)
    db_session.commit()

    retrieved_word = get_word(db_session, test_word.id, user2.id)
    assert retrieved_word is None

def test_get_words_by_owner(db_session, test_user, test_word):
    # Создаем второе слово
    word2 = schemas.WordCreate(text="world", translation="мир")
    run_async(create_word(db_session, word2, test_user.id))

    result = get_words_by_owner(db_session, test_user.id)
    assert len(result["items"]) == 2
    assert result["total"] == 2

def test_get_words_by_owner_pagination(db_session, test_user):
    # Создаем несколько слов
    for i in range(5):
        word_data = schemas.WordCreate(text=f"word{i}", translation=f"слово{i}")
        run_async(create_word(db_session, word_data, test_user.id))

    # Тестируем пагинацию
    result1 = get_words_by_owner(db_session, test_user.id, skip=0, limit=3)
    assert len(result1["items"]) == 3
    assert result1["total"] == 5

    result2 = get_words_by_owner(db_session, test_user.id, skip=3, limit=3)
    assert len(result2["items"]) == 2
    assert result2["total"] == 5

def test_get_words_by_owner_filter(db_session, test_user):
    # Создаем слова с разными статусами
    word1 = schemas.WordCreate(text="learned", translation="выученное", is_learned=True)
    word2 = schemas.WordCreate(text="unlearned", translation="невыученное", is_learned=False)
    run_async(create_word(db_session, word1, test_user.id))
    run_async(create_word(db_session, word2, test_user.id))

    # Фильтр по выученным словам
    result = get_words_by_owner(db_session, test_user.id, is_learned=True)
    assert len(result["items"]) == 1
    assert result["items"][0].text == "learned"

    # Фильтр по невыученным словам
    result = get_words_by_owner(db_session, test_user.id, is_learned=False)
    assert len(result["items"]) == 1
    assert result["items"][0].text == "unlearned"

def test_get_words_by_owner_search(db_session, test_user):
    # Создаем слова для поиска
    word1 = schemas.WordCreate(text="apple", translation="яблоко")
    word2 = schemas.WordCreate(text="banana", translation="банан")
    run_async(create_word(db_session, word1, test_user.id))
    run_async(create_word(db_session, word2, test_user.id))

    # Поиск по тексту
    result = get_words_by_owner(db_session, test_user.id, search="app")
    assert len(result["items"]) == 1
    assert result["items"][0].text == "apple"

    # Поиск по переводу
    result = get_words_by_owner(db_session, test_user.id, search="бан")
    assert len(result["items"]) == 1
    assert result["items"][0].translation == "банан"

def test_delete_word(db_session, test_word):
    result = delete_word(db_session, test_word.id, test_word.owner_id)
    assert result == True

    # Проверяем что слово удалено
    retrieved_word = get_word(db_session, test_word.id, test_word.owner_id)
    assert retrieved_word is None

def test_delete_word_not_found(db_session, test_user):
    result = delete_word(db_session, 999, test_user.id)
    assert result == False

def test_review_word(db_session, test_word):
    # Повторяем слово несколько раз
    for _ in range(SRS_MAX_LEVEL - 1):
        word = review_word(db_session, test_word.id, test_word.owner_id)
        assert word.review_count == _ + 1
        assert word.is_learned == False

    # Последний повтор - должно пометиться как выученное
    word = review_word(db_session, test_word.id, test_word.owner_id)
    assert word.review_count == SRS_MAX_LEVEL
    assert word.is_learned == True

def test_review_word_not_found(db_session, test_user):
    word = review_word(db_session, 999, test_user.id)
    assert word is None

def test_toggle_learned(db_session, test_word):
    # Помечаем как выученное
    word = toggle_learned(db_session, test_word.id, test_word.owner_id, True)
    assert word.is_learned == True

    # Помечаем как невыученное
    word = toggle_learned(db_session, test_word.id, test_word.owner_id, False)
    assert word.is_learned == False

def test_toggle_learned_not_found(db_session, test_user):
    word = toggle_learned(db_session, 999, test_user.id, True)
    assert word is None

def test_get_random_unlearned_word(db_session, test_user):
    # Создаем несколько невыученных слов
    for i in range(3):
        word_data = schemas.WordCreate(text=f"word{i}", translation=f"слово{i}")
        run_async(create_word(db_session, word_data, test_user.id))

    word = get_random_unlearned_word(db_session, test_user.id)
    assert word is not None
    assert word.is_learned == False

def test_get_random_unlearned_word_none(db_session, test_user):
    # Создаем выученное слово
    word_data = schemas.WordCreate(text="learned", translation="выученное", is_learned=True)
    run_async(create_word(db_session, word_data, test_user.id))

    word = get_random_unlearned_word(db_session, test_user.id)
    assert word is None

def test_get_words_stats(db_session, test_user):
    # Создаем слова с разными статусами
    word1 = schemas.WordCreate(text="learned", translation="выученное", is_learned=True)
    word2 = schemas.WordCreate(text="unlearned", translation="невыученное", is_learned=False)
    run_async(create_word(db_session, word1, test_user.id))
    run_async(create_word(db_session, word2, test_user.id))

    stats = get_words_stats(db_session, test_user.id)
    assert stats["total"] == 2
    assert stats["learned"] == 1
    assert stats["remaining"] == 1