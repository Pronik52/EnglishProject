"""Тесты тарифа: демо-покупка закрыта флагом, статус и лимиты доступны.

Оплата убрана из интерфейса, но эндпоинты остаются вызываемыми напрямую.
Именно поэтому здесь проверяется, что без BILLING_DEMO_ENABLED включить
Premium нельзя: отсутствие кнопки — не защита.
"""

import pytest

from app.crud import words as crud_words


def _headers(client, test_user):
    login = client.post("/api/v1/auth/token",
                        data={"username": test_user.email, "password": "secret"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# --- демо-покупка выключена по умолчанию ---

def test_activate_is_hidden_without_demo_flag(client, test_user, monkeypatch):
    monkeypatch.delenv("BILLING_DEMO_ENABLED", raising=False)

    resp = client.post("/api/v1/billing/activate", json={"plan": 1},
                       headers=_headers(client, test_user))

    assert resp.status_code == 404


def test_deactivate_is_hidden_without_demo_flag(client, test_user, monkeypatch):
    monkeypatch.delenv("BILLING_DEMO_ENABLED", raising=False)

    resp = client.post("/api/v1/billing/deactivate",
                       headers=_headers(client, test_user))

    assert resp.status_code == 404


def test_activate_does_not_grant_premium_when_disabled(client, test_user, db_session, monkeypatch):
    monkeypatch.delenv("BILLING_DEMO_ENABLED", raising=False)

    client.post("/api/v1/billing/activate", json={"plan": 12},
                headers=_headers(client, test_user))

    db_session.refresh(test_user)
    assert test_user.is_premium is False


@pytest.mark.parametrize("flag", ["1", "true", "yes", "TRUE"])
def test_activate_works_when_demo_is_enabled(client, test_user, flag, monkeypatch):
    monkeypatch.setenv("BILLING_DEMO_ENABLED", flag)

    resp = client.post("/api/v1/billing/activate", json={"plan": 1},
                       headers=_headers(client, test_user))

    assert resp.status_code == 200
    assert resp.json()["is_premium"] is True


def test_arbitrary_flag_value_does_not_enable_demo(client, test_user, monkeypatch):
    monkeypatch.setenv("BILLING_DEMO_ENABLED", "maybe")

    resp = client.post("/api/v1/billing/activate", json={"plan": 1},
                       headers=_headers(client, test_user))

    assert resp.status_code == 404


# --- статус остаётся доступен: по нему считается остаток дневной квоты ---

def test_status_is_available_without_demo_flag(client, test_user, monkeypatch):
    monkeypatch.delenv("BILLING_DEMO_ENABLED", raising=False)

    resp = client.get("/api/v1/billing/status", headers=_headers(client, test_user))

    assert resp.status_code == 200
    data = resp.json()
    assert data["is_premium"] is False
    assert data["daily_limit"] == crud_words.DAILY_WORD_LIMIT
    assert data["remaining"] == crud_words.DAILY_WORD_LIMIT


def test_status_requires_auth(client):
    assert client.get("/api/v1/billing/status").status_code == 401


# --- лимиты как защита от злоупотреблений, а не как тариф ---

def test_limits_are_high_enough_not_to_block_normal_use(client, test_user):
    """Пороги не должны ощущаться на обычном занятии.

    Раньше здесь стояли 10 слов и 20 проверок в день — упереться в них
    получалось на первом же занятии, и это работало как платная стена.
    """
    assert crud_words.DAILY_WORD_LIMIT >= 50
    assert crud_words.DAILY_DESCRIBE_LIMIT >= 50
    assert crud_words.REGEN_LIMIT >= 10


def test_limit_message_does_not_advertise_premium(client, test_user, monkeypatch):
    monkeypatch.setattr(crud_words, "DAILY_WORD_LIMIT", 1)

    headers = _headers(client, test_user)
    client.post("/api/v1/words", json={"text": "apple", "translation": "яблоко"},
                headers=headers)
    resp = client.post("/api/v1/words", json={"text": "bread", "translation": "хлеб"},
                       headers=headers)

    assert resp.status_code == 402
    message = resp.json()["error"]["message"]
    assert "Premium" not in message
    assert "завтра" in message
