"""Тесты режима «опиши картинку»: мягкая оценка, лимит, журнал повторов."""

import pytest

from app import evaluator, models, schemas
from app.crud.words import (
    DAILY_DESCRIBE_LIMIT, SRS_MAX_LEVEL, count_describes_today,
    create_word, describe_word,
)
from tests.conftest import run_async


def _word_with_scene(db_session, user, text="lighthouse", translation="маяк"):
    word = run_async(create_word(
        db_session, schemas.WordCreate(text=text, translation=translation), user.id
    ))
    word.scene_prompt = "an old man and two boys looking at a lighthouse by the sea"
    word.phrase = "My grandfather lived near a lighthouse."
    db_session.commit()
    return word


# --- офлайн-проверка (ИИ недоступен) ---

def test_offline_counts_answer_with_target_word():
    v = evaluator._offline_verdict("lighthouse", "I see a lighthouse near the sea")
    assert v["used_word"] is True
    assert v["grade"] >= evaluator.PASS_GRADE


def test_offline_rejects_answer_without_target_word():
    v = evaluator._offline_verdict("lighthouse", "I see a big house")
    assert v["used_word"] is False
    assert v["grade"] == 0


def test_word_is_used_catches_word_forms():
    # Пользователь почти никогда не пишет слово ровно в словарной форме.
    assert evaluator._word_is_used("build", "they are building a house")
    assert evaluator._word_is_used("city", "the cities are big")
    assert not evaluator._word_is_used("lighthouse", "a dog runs")


def test_prompt_does_not_require_time_that_is_not_visible_in_picture():
    """Эталонная фраза — контекст, а не список обязательных деталей.

    Точное время нельзя восстановить по обычной сцене завтрака, поэтому за
    ответ ``We have breakfast together`` модель не должна придираться.
    """
    prompt = evaluator._build_prompt(
        word="breakfast",
        translation="завтрак",
        phrase="We have breakfast at eight o'clock.",
        scene="a man and a woman having breakfast together in a sunny kitchen",
        level="A1",
        answer="We have breakfast together",
    )

    assert "NOT a checklist" in prompt
    assert "do not criticise a missing exact time" in prompt
    assert "Missing optional scene details are NOT grammar issues" in prompt
    assert "Otherwise return an empty string" in prompt


def test_unverifiable_time_nitpick_is_removed_from_model_verdict():
    verdict = evaluator._remove_unverifiable_nitpicks({
        "grade": 2,
        "used_word": True,
        "feedback_ru": "Отлично, но не указано время.",
        "grammar_ru": ["Не хватает указания на время"],
        "better_en": "We have breakfast together at eight o'clock.",
        "offline": False,
    }, scene="a man and a woman having breakfast together in a sunny kitchen")

    assert verdict["grammar_ru"] == []
    assert verdict["better_en"] == ""
    assert "врем" not in verdict["feedback_ru"].lower()


def test_time_may_be_checked_when_a_clock_is_visible():
    verdict = evaluator._remove_unverifiable_nitpicks({
        "grade": 2,
        "feedback_ru": "Смысл передан.",
        "grammar_ru": ["Проверьте указанное время"],
        "better_en": "We have breakfast at eight o'clock.",
    }, scene="a wall clock visibly shows eight as two people eat breakfast")

    assert verdict["grammar_ru"] == ["Проверьте указанное время"]
    assert verdict["better_en"] == "We have breakfast at eight o'clock."


def test_exact_reference_answer_always_gets_three_stars():
    verdict = evaluator._finalize_model_verdict({
        "grade": 2,
        "used_word": True,
        "feedback_ru": "Слово использовано правильно.",
        "grammar_ru": [],
        "better_en": "",
        "offline": False,
    }, scene="milk bottles in a kitchen",
       answer="the PRICE of milk went up",
       phrase="The price of milk went up.")

    assert verdict["grade"] == 3
    assert verdict["feedback_ru"] == "Отлично, ответ полностью верный!"


def test_different_answer_keeps_model_grade():
    verdict = evaluator._finalize_model_verdict({
        "grade": 2,
        "used_word": True,
        "feedback_ru": "Смысл передан.",
        "grammar_ru": [],
        "better_en": "",
    }, scene="milk bottles in a kitchen",
       answer="Milk is more expensive now",
       phrase="The price of milk went up.")

    assert verdict["grade"] == 2


def test_exact_reference_answer_gets_three_stars_offline(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    verdict = run_async(evaluator.evaluate_description(
        word="price",
        translation="цена",
        phrase="The price of milk went up.",
        scene="milk bottles in a kitchen",
        level="A1",
        answer="The price of milk went up",
    ))

    assert verdict["offline"] is True
    assert verdict["grade"] == 3


def test_empty_answer_is_rejected_without_calling_ai():
    v = run_async(evaluator.evaluate_description(
        word="lighthouse", translation="маяк", phrase="p", scene="s",
        level="A1", answer="   "
    ))
    assert v["grade"] == 0
    assert v["offline"] is True


# --- влияние на повторы ---

def test_good_description_advances_srs(db_session, test_user, monkeypatch):
    word = _word_with_scene(db_session, test_user)
    before = word.srs_level or 0

    async def verdict(**kwargs):
        return {"grade": 3, "used_word": True, "feedback_ru": "Отлично!",
                "grammar_ru": [], "better_en": "", "offline": False}

    monkeypatch.setattr("app.crud.words.evaluate_description", verdict)
    status, updated, v = run_async(describe_word(
        db_session, word.id, test_user.id, "An old man looks at the lighthouse.",
    ))
    assert status == "ok"
    assert updated.srs_level == before + 1
    assert v["grade"] == 3


def test_grammar_mistakes_do_not_block_progress(db_session, test_user, monkeypatch):
    """Решение по продукту: оценка мягкая. Замечания по грамматике
    показываем, но повтор всё равно засчитываем."""
    word = _word_with_scene(db_session, test_user)

    async def verdict(**kwargs):
        return {"grade": 2, "used_word": True, "feedback_ru": "Смысл передан верно.",
                "grammar_ru": ["Пропущен артикль: a lighthouse"],
                "better_en": "A man looks at a lighthouse.", "offline": False}

    monkeypatch.setattr("app.crud.words.evaluate_description", verdict)
    status, updated, v = run_async(describe_word(
        db_session, word.id, test_user.id, "man look at lighthouse",
    ))
    assert status == "ok"
    assert updated.srs_level == 1          # прогресс есть
    assert v["grammar_ru"]                  # и подсказка тоже есть


def test_missing_word_resets_progress(db_session, test_user, monkeypatch):
    word = _word_with_scene(db_session, test_user)
    word.srs_level = 3
    db_session.commit()

    async def verdict(**kwargs):
        return {"grade": 0, "used_word": False, "feedback_ru": "Слова нет в ответе.",
                "grammar_ru": [], "better_en": "", "offline": False}

    monkeypatch.setattr("app.crud.words.evaluate_description", verdict)
    status, updated, _ = run_async(describe_word(
        db_session, word.id, test_user.id, "some people near the water",
    ))
    assert status == "ok"
    assert updated.srs_level == 0


def test_word_without_scene_cannot_be_described(db_session, test_user):
    word = run_async(create_word(
        db_session, schemas.WordCreate(text="apple", translation="яблоко"), test_user.id
    ))
    word.scene_prompt = None
    db_session.commit()

    status, _, _ = run_async(describe_word(db_session, word.id, test_user.id, "an apple"))
    assert status == "no_scene"


def test_other_users_word_is_not_found(db_session, test_user):
    stranger = models.User(email="stranger@example.com", hashed_password="x")
    db_session.add(stranger)
    db_session.commit()
    word = _word_with_scene(db_session, stranger)

    status, _, _ = run_async(describe_word(db_session, word.id, test_user.id, "a lighthouse"))
    assert status == "not_found"


# --- журнал повторов и дневной лимит ---

def test_review_is_written_to_log(db_session, test_user, monkeypatch):
    word = _word_with_scene(db_session, test_user)

    async def verdict(**kwargs):
        return {"grade": 2, "used_word": True, "feedback_ru": "ок",
                "grammar_ru": [], "better_en": "", "offline": False}

    monkeypatch.setattr("app.crud.words.evaluate_description", verdict)
    run_async(describe_word(db_session, word.id, test_user.id, "a lighthouse by the sea"))

    log = db_session.query(models.ReviewLog).filter_by(word_id=word.id).one()
    assert log.mode == "describe"
    assert log.correct is True
    assert log.grade == 2
    assert log.answer_text == "a lighthouse by the sea"
    assert log.srs_level_after == 1


def test_daily_limit_blocks_free_user(db_session, test_user, monkeypatch):
    word = _word_with_scene(db_session, test_user)

    async def verdict(**kwargs):
        return {"grade": 2, "used_word": True, "feedback_ru": "ок",
                "grammar_ru": [], "better_en": "", "offline": False}

    monkeypatch.setattr("app.crud.words.evaluate_description", verdict)

    for _ in range(DAILY_DESCRIBE_LIMIT):
        status, _, _ = run_async(describe_word(db_session, word.id, test_user.id, "a lighthouse"))
        assert status == "ok"

    assert count_describes_today(db_session, test_user.id) == DAILY_DESCRIBE_LIMIT
    status, _, _ = run_async(describe_word(db_session, word.id, test_user.id, "a lighthouse"))
    assert status == "limit"


def test_premium_has_no_daily_limit(db_session, test_user, monkeypatch):
    word = _word_with_scene(db_session, test_user)

    async def verdict(**kwargs):
        return {"grade": 2, "used_word": True, "feedback_ru": "ок",
                "grammar_ru": [], "better_en": "", "offline": False}

    monkeypatch.setattr("app.crud.words.evaluate_description", verdict)
    for _ in range(DAILY_DESCRIBE_LIMIT + 3):
        status, _, _ = run_async(describe_word(
            db_session, word.id, test_user.id, "a lighthouse", is_premium=True
        ))
        assert status == "ok"


def test_quiz_answer_is_also_logged(db_session, test_user):
    from app.crud.words import answer_word

    word = _word_with_scene(db_session, test_user)
    answer_word(db_session, word.id, test_user.id, correct=True)

    log = db_session.query(models.ReviewLog).filter_by(word_id=word.id).one()
    assert log.mode == "choice"
    assert log.correct is True


# --- HTTP ---

def test_describe_endpoint_returns_verdict(client, db_session, test_user, monkeypatch):
    word = _word_with_scene(db_session, test_user)

    async def verdict(**kwargs):
        return {"grade": 3, "used_word": True, "feedback_ru": "Отличное описание!",
                "grammar_ru": [], "better_en": "An old man watches the lighthouse.",
                "offline": False}

    monkeypatch.setattr("app.crud.words.evaluate_description", verdict)

    login = client.post("/api/v1/auth/token",
                        data={"username": test_user.email, "password": "secret"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.post(f"/api/v1/words/{word.id}/describe",
                       json={"text": "An old man looks at the lighthouse."},
                       headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"]["grade"] == 3
    assert data["verdict"]["correct"] is True
    assert data["word"]["srs_level"] == 1
    assert data["describes_left"] == DAILY_DESCRIBE_LIMIT - 1
    # Эталон сцены не должен утекать клиенту даже здесь.
    assert "scene_prompt" not in data["word"]


def test_describe_endpoint_rejects_empty_text(client, db_session, test_user):
    word = _word_with_scene(db_session, test_user)
    login = client.post("/api/v1/auth/token",
                        data={"username": test_user.email, "password": "secret"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    resp = client.post(f"/api/v1/words/{word.id}/describe",
                       json={"text": "   "}, headers=headers)
    assert resp.status_code == 422
    assert "Опишите" in str(resp.json()["error"]["details"])
