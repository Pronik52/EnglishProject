import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app import models

# Настройка тестовой базы данных
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Создание таблиц в тестовой базе
Base.metadata.create_all(bind=engine)

# Фикстура для тестового клиента
@pytest.fixture(scope="module")
def client():
    # Переопределяем зависимость get_db для тестов
    def override_get_db():
        try:
            db = TestingSessionLocal()
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

# Фикстура для тестовой сессии базы данных
@pytest.fixture(scope="function")
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

# Фикстура для тестового пользователя
@pytest.fixture(scope="function")
def test_user(db_session):
    user = models.User(
        email="test@example.com",
        hashed_password="$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"  # "secret"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

# Фикстура для тестового слова
@pytest.fixture(scope="function")
def test_word(db_session, test_user):
    word = models.Word(
        text="hello",
        translation="привет",
        owner_id=test_user.id
    )
    db_session.add(word)
    db_session.commit()
    db_session.refresh(word)
    return word