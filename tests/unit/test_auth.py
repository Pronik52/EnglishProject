import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import models

client = TestClient(app)

def test_register_user(db_session):
    # Тестируем регистрацию нового пользователя
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "newuser@example.com", "password": "ValidPass123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert "id" in data
    assert "created_at" in data
    assert "password" not in data

def test_register_user_weak_password(db_session):
    # Тестируем регистрацию со слабым паролем
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "weak"}
    )
    assert response.status_code == 422
    data = response.json()
    assert "validation_error" in data["error"]["code"]
    assert "Пароль должен содержать минимум 8 символов" in str(data["error"]["details"])

def test_register_user_invalid_email(db_session):
    # Тестируем регистрацию с невалидным email
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "invalid-email", "password": "ValidPass123"}
    )
    assert response.status_code == 422
    data = response.json()
    assert "validation_error" in data["error"]["code"]

def test_register_user_duplicate_email(db_session, test_user):
    # Тестируем регистрацию с уже существующим email
    response = client.post(
        "/api/v1/auth/register",
        json={"email": test_user.email, "password": "ValidPass123"}
    )
    assert response.status_code == 400
    data = response.json()
    assert "Email уже зарегистрирован" in data["error"]["message"]

def test_login_user(db_session, test_user):
    # Browser login не раскрывает JWT в JSON, а устанавливает две cookie.
    response = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.email, "password": "secret"}
    )
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert "access_token=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "csrf_token=" in cookie

def test_session_cookies_are_visible_on_the_whole_site(db_session, test_user):
    """csrf_token обязан иметь path=/, иначе SPA на /app его не прочитает.

    С path=/api/v1 браузер продолжает слать cookie на API сам, но не отдаёт её
    в document.cookie на странице /app — фронтенд не может проставить
    X-CSRF-Token, и каждый POST отбивается middleware с 403.
    """
    response = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.email, "password": "secret"},
    )
    assert response.status_code == 204

    for cookie in response.headers.get_list("set-cookie"):
        assert "Path=/;" in cookie or cookie.endswith("Path=/")


def test_login_user_invalid_password(db_session, test_user):
    # Тестируем логин с неверным паролем
    response = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.email, "password": "wrongpassword"}
    )
    assert response.status_code == 401
    data = response.json()
    assert "Неверный email или пароль" in data["error"]["message"]

def test_get_current_user(db_session, test_user):
    # TestClient хранит cookie после login и отправляет их на /me сам.
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.email, "password": "secret"}
    )
    assert login_response.status_code == 204

    # Теперь получаем информацию о текущем пользователе
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
    assert data["id"] == test_user.id


def test_logout_removes_cookie_session(db_session, test_user):
    client.post(
        "/api/v1/auth/login",
        data={"username": test_user.email, "password": "secret"},
    )
    csrf = client.cookies.get("csrf_token")

    response = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 204

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_cookie_session_requires_csrf_header_for_changes(db_session, test_user):
    client.post(
        "/api/v1/auth/login",
        data={"username": test_user.email, "password": "secret"},
    )

    response = client.patch(
        "/api/v1/auth/level",
        json={"level": "B1"},
    )
    assert response.status_code == 403

    response = client.patch(
        "/api/v1/auth/level",
        json={"level": "B1"},
        headers={"X-CSRF-Token": client.cookies.get("csrf_token")},
    )
    assert response.status_code == 200
    assert response.json()["level"] == "B1"


def test_token_endpoint_returns_bearer_jwt(db_session, test_user):
    response = client.post(
        "/api/v1/auth/token",
        data={"username": test_user.email, "password": "secret"},
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert "access_token" in response.json()
