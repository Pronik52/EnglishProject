"""Тесты учебной сессии: отбор по срокам, лестница режимов, варианты ответа."""

from datetime import datetime, timedelta

import pytest

from app import models
from app.crud import study as crud_study
from app.crud.words import get_words_stats


def _word(db_session, user, text, translation="перевод", *, srs_level=0,
          due_at=None, is_learned=False, image_url=None, image_status="none"):
    """Слово с заданным состоянием SRS — без генерации фраз и картинок."""
    word = models.Word(
        text=text, translation=translation, owner_id=user.id,
        srs_level=srs_level, due_at=due_at, is_learned=is_learned,
        phrase=f"A sentence with {text}.", scene_prompt="a scene",
        image_url=image_url, image_status=image_status,
    )
    db_session.add(word)
    db_session.commit()
    db_session.refresh(word)
    return word


def _headers(client, test_user):
    login = client.post("/api/v1/auth/token",
                        data={"username": test_user.email, "password": "secret"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# --- 1. отбор слов ---

def test_session_takes_only_due_words(db_session, test_user):
    later = datetime.utcnow() + timedelta(days=3)
    _word(db_session, test_user, "apple", due_at=datetime.utcnow() - timedelta(days=1))
    _word(db_session, test_user, "bread", due_at=None)          # новое слово — тоже к повтору
    _word(db_session, test_user, "cloud", due_at=later)         # ещё рано

    session = crud_study.build_session(db_session, test_user.id)

    texts = {c["word"].text for c in session["cards"]}
    assert texts == {"apple", "bread"}
    assert session["ahead"] is False


def test_session_skips_learned_words(db_session, test_user):
    _word(db_session, test_user, "apple", due_at=datetime.utcnow() - timedelta(days=1))
    _word(db_session, test_user, "learned", is_learned=True,
          due_at=datetime.utcnow() - timedelta(days=5))

    session = crud_study.build_session(db_session, test_user.id)

    assert [c["word"].text for c in session["cards"]] == ["apple"]


def test_session_orders_most_overdue_first(db_session, test_user):
    now = datetime.utcnow()
    _word(db_session, test_user, "recent", due_at=now - timedelta(hours=1))
    _word(db_session, test_user, "oldest", due_at=now - timedelta(days=10))
    _word(db_session, test_user, "middle", due_at=now - timedelta(days=2))

    session = crud_study.build_session(db_session, test_user.id)

    assert [c["word"].text for c in session["cards"]] == ["oldest", "middle", "recent"]


def test_session_respects_size_but_reports_full_due_count(db_session, test_user):
    past = datetime.utcnow() - timedelta(days=1)
    for i in range(9):
        _word(db_session, test_user, f"word{i}", due_at=past)

    session = crud_study.build_session(db_session, test_user.id, size=4)

    assert len(session["cards"]) == 4
    # due_total считает всё, что ждёт повторения, а не только попавшее в сессию:
    # по этой разнице клиент показывает «осталось ещё N».
    assert session["due_total"] == 9


def test_session_size_is_clamped_to_maximum(db_session, test_user):
    past = datetime.utcnow() - timedelta(days=1)
    for i in range(crud_study.SESSION_MAX_SIZE + 5):
        _word(db_session, test_user, f"word{i}", due_at=past)

    session = crud_study.build_session(db_session, test_user.id, size=999)

    assert len(session["cards"]) == crud_study.SESSION_MAX_SIZE


def test_empty_session_when_nothing_is_due(db_session, test_user):
    _word(db_session, test_user, "apple",
          due_at=datetime.utcnow() + timedelta(days=3))

    session = crud_study.build_session(db_session, test_user.id)

    # Пустая сессия — штатный ответ «на сегодня всё», а не ошибка.
    assert session["cards"] == []
    assert session["due_total"] == 0


def test_ahead_session_ignores_due_date(db_session, test_user):
    _word(db_session, test_user, "apple",
          due_at=datetime.utcnow() + timedelta(days=30))

    session = crud_study.build_session(db_session, test_user.id, ahead=True)

    assert [c["word"].text for c in session["cards"]] == ["apple"]
    assert session["ahead"] is True
    assert session["due_total"] == 0    # сверх плана не меняет числа на дашборде


def test_ahead_session_still_skips_learned(db_session, test_user):
    _word(db_session, test_user, "done", is_learned=True, srs_level=5)

    session = crud_study.build_session(db_session, test_user.id, ahead=True)

    assert session["cards"] == []


def test_session_never_returns_other_users_words(db_session, test_user):
    stranger = models.User(email="other@example.com", hashed_password="x")
    db_session.add(stranger)
    db_session.commit()
    _word(db_session, stranger, "secret")
    _word(db_session, test_user, "mine")

    session = crud_study.build_session(db_session, test_user.id)

    assert [c["word"].text for c in session["cards"]] == ["mine"]


def test_due_count_matches_dashboard_stats(db_session, test_user):
    """Число на дашборде и состав сессии считаются одним правилом.

    Раньше условие «пора повторить» было записано в двух местах, и цифры могли
    разъехаться: дашборд обещал N слов, а тренировка давала другое.
    """
    now = datetime.utcnow()
    _word(db_session, test_user, "a", due_at=now - timedelta(days=1))
    _word(db_session, test_user, "b", due_at=None)
    _word(db_session, test_user, "c", due_at=now + timedelta(days=5))
    _word(db_session, test_user, "d", is_learned=True)

    session = crud_study.build_session(db_session, test_user.id)
    stats = get_words_stats(db_session, owner_id=test_user.id)

    assert session["due_total"] == stats["due"] == 2


# --- 2. лестница сложности ---

@pytest.mark.parametrize("srs_level,expected", [
    (0, crud_study.MODE_CHOICE),
    (1, crud_study.MODE_CHOICE),
    (2, crud_study.MODE_TYPE),
    (3, crud_study.MODE_TYPE),
    (4, crud_study.MODE_DESCRIBE),
])
def test_mode_follows_srs_level(db_session, test_user, srs_level, expected):
    # Отвлекатели нужны для choice, иначе карточка честно понизится до type.
    for i in range(5):
        _word(db_session, test_user, f"filler{i}",
              due_at=datetime.utcnow() + timedelta(days=99))
    _word(db_session, test_user, "target", srs_level=srs_level,
          image_url="/media/scenes/x.jpg", image_status="ready")

    session = crud_study.build_session(db_session, test_user.id)
    card = next(c for c in session["cards"] if c["word"].text == "target")

    assert card["mode"] == expected


def test_new_word_is_never_asked_as_description(db_session, test_user):
    """Главный барьер входа: первая карточка не должна требовать сочинения."""
    for i in range(5):
        _word(db_session, test_user, f"filler{i}")
    _word(db_session, test_user, "fresh", srs_level=0,
          image_url="/media/scenes/x.jpg", image_status="ready")

    session = crud_study.build_session(db_session, test_user.id)
    card = next(c for c in session["cards"] if c["word"].text == "fresh")

    assert card["mode"] == crud_study.MODE_CHOICE


def test_describe_falls_back_to_type_without_picture(db_session, test_user):
    _word(db_session, test_user, "target", srs_level=5, image_status="none")

    session = crud_study.build_session(db_session, test_user.id)

    assert session["cards"][0]["mode"] == crud_study.MODE_TYPE


def test_describe_kept_while_picture_is_being_drawn(db_session, test_user):
    _word(db_session, test_user, "target", srs_level=4, image_status="pending")

    session = crud_study.build_session(db_session, test_user.id)

    # Картинка вот-вот появится — карточка подождёт её, а не сменит режим.
    assert session["cards"][0]["mode"] == crud_study.MODE_DESCRIBE


def test_choice_falls_back_to_type_without_distractors(db_session, test_user):
    """Словарь почти пуст и каталог не наполнен — выбирать не из чего."""
    _word(db_session, test_user, "alone", srs_level=0)

    session = crud_study.build_session(db_session, test_user.id)

    assert session["cards"][0]["mode"] == crud_study.MODE_TYPE
    assert session["cards"][0]["options"] is None


# --- 3. варианты ответа ---

def test_choice_card_has_four_options_including_the_answer(db_session, test_user):
    for i in range(5):
        _word(db_session, test_user, f"filler{i}")
    _word(db_session, test_user, "target", srs_level=0)

    session = crud_study.build_session(db_session, test_user.id)
    card = next(c for c in session["cards"] if c["word"].text == "target")

    assert len(card["options"]) == crud_study.OPTIONS_COUNT
    assert "target" in card["options"]
    assert len(set(card["options"])) == crud_study.OPTIONS_COUNT   # без повторов


def test_options_never_repeat_the_answer_as_distractor(db_session, test_user):
    for i in range(6):
        _word(db_session, test_user, f"filler{i}")
    _word(db_session, test_user, "target", srs_level=0)

    session = crud_study.build_session(db_session, test_user.id)
    card = next(c for c in session["cards"] if c["word"].text == "target")

    assert card["options"].count("target") == 1


def test_distractors_topped_up_from_catalog(db_session, test_user):
    """Своих слов мало — варианты добираются каталогом того же уровня."""
    for text in ("apple", "bread", "cloud", "dream"):
        db_session.add(models.CatalogWord(
            text=text, translation="перевод", level="A1", frequency_rank=1
        ))
    db_session.commit()
    _word(db_session, test_user, "alone", srs_level=0)

    session = crud_study.build_session(db_session, test_user.id, level="A1")
    card = session["cards"][0]

    assert card["mode"] == crud_study.MODE_CHOICE
    assert len(card["options"]) == crud_study.OPTIONS_COUNT


def test_options_are_present_even_for_non_choice_cards(db_session, test_user):
    """Клиент может вручную переключить режим — варианты должны быть готовы.

    Собрать их на клиенте больше не из чего: пул отвлекателей живёт на сервере.
    """
    for i in range(5):
        _word(db_session, test_user, f"filler{i}")
    _word(db_session, test_user, "target", srs_level=3)   # режим type

    session = crud_study.build_session(db_session, test_user.id)
    card = next(c for c in session["cards"] if c["word"].text == "target")

    assert card["mode"] == crud_study.MODE_TYPE
    assert card["options"] and len(card["options"]) == crud_study.OPTIONS_COUNT


def test_distractor_pool_is_built_once_per_session(db_session, test_user):
    """Пул отвлекателей не должен собираться на каждую карточку (N+1)."""
    for i in range(12):
        _word(db_session, test_user, f"word{i}", srs_level=0)

    calls = {"n": 0}
    original = crud_study._distractor_pool

    def counting(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    crud_study._distractor_pool = counting
    try:
        session = crud_study.build_session(db_session, test_user.id, size=12)
    finally:
        crud_study._distractor_pool = original

    assert len(session["cards"]) == 12
    assert calls["n"] == 1


# --- 4. эндпоинт ---

def test_session_endpoint_returns_cards(client, test_user, db_session):
    for i in range(5):
        _word(db_session, test_user, f"filler{i}")
    _word(db_session, test_user, "target", srs_level=0)

    resp = client.get("/api/v1/study/session", headers=_headers(client, test_user))

    assert resp.status_code == 200
    data = resp.json()
    assert data["due_total"] == 6
    assert data["ahead"] is False
    card = next(c for c in data["cards"] if c["word"]["text"] == "target")
    assert card["mode"] == "choice"
    assert len(card["options"]) == 4
    # scene_prompt — эталон для режима описания, клиенту его не отдаём.
    assert "scene_prompt" not in card["word"]


def test_session_endpoint_requires_auth(client):
    assert client.get("/api/v1/study/session").status_code == 401


def test_session_endpoint_rejects_oversized_request(client, test_user):
    resp = client.get(f"/api/v1/study/session?size={crud_study.SESSION_MAX_SIZE + 1}",
                      headers=_headers(client, test_user))
    assert resp.status_code == 422


def test_answering_removes_word_from_todays_session(client, test_user, db_session):
    """Сквозная проверка: ответ уводит слово из сегодняшней сессии."""
    headers = _headers(client, test_user)
    word = _word(db_session, test_user, "apple", srs_level=0)

    first = client.get("/api/v1/study/session", headers=headers).json()
    assert [c["word"]["text"] for c in first["cards"]] == ["apple"]

    client.patch(f"/api/v1/words/{word.id}/answer", json={"correct": True},
                 headers=headers)

    second = client.get("/api/v1/study/session", headers=headers).json()
    assert second["cards"] == []
    assert second["due_total"] == 0
