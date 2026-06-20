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
    # Сначала создаем пользователя через CRUD (так как у нас нет хеширования пароля в тесте)
    from app.crud.users import create_user
    from app.schemas import UserCreate

    user_data = UserCreate(email="login@example.com", password="ValidPass123")
    user = create_user(db_session, user=user_data)

    # Теперь тестируем логин
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "login@example.com", "password": "ValidPass123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

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
    # Сначала получаем токен
    login_response = client.post(
        "/api/v1/auth/login",
        data={"username": test_user.email, "password": "secret"}
    )
    token = login_response.json()["access_token"]

    # Теперь получаем информацию о текущем пользователе
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
    assert data["id"] == test_user.id