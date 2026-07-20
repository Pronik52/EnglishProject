import asyncio
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app import models
from app.crud import words as crud_words

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


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Подменяем источник базы СРАЗУ при импорте conftest, а не только внутри
# фикстуры client. Причина: тестовые модули заводят собственный
# `client = TestClient(app)` на уровне модуля, мимо фикстуры. Пока подмена жила
# в фикстуре, такие клиенты работали с настоящей базой из DATABASE_URL — то
# есть прогон pytest писал тестовых пользователей в рабочую базу.
app.dependency_overrides[get_db] = override_get_db

# Подмены get_db мало: фоновая генерация картинки работает не по Depends, а
# открывает сессию сама через SessionLocal — её надо перенаправить отдельно,
# иначе фоновая задача в тестах пойдёт в рабочую базу.
crud_words.SessionLocal = TestingSessionLocal

# Тесты не должны ходить в интернет: иначе они медленные, зависят от наличия
# сети и жгут квоты внешних сервисов. Отключаем все три внешних вызова разом.
#
# Groq и генератор картинок проверяют настройки в момент вызова, поэтому им
# достаточно переменных окружения — код при этом честно идёт по своей штатной
# офлайн-ветке. Переводчик такой настройки не имеет, его подменяем напрямую,
# причём в обоих модулях, которые импортировали функцию себе в пространство имён.
@pytest.fixture(autouse=True)
def offline_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("IMAGE_PROVIDER", "off")
    # Картинки кешируются на диске по хешу сцены. Без изоляции тесты видели бы
    # файлы, сгенерированные при обычной работе приложения, и «уже готовая»
    # картинка ломала бы проверки состояния pending.
    monkeypatch.setattr("app.image_generator.SCENES_DIR", tmp_path / "scenes", raising=False)
    monkeypatch.setattr("app.phrases.translate_to_ru", lambda text: "", raising=False)
    monkeypatch.setattr("app.crud.words.translate_to_ru", lambda text: "", raising=False)
    # В бою генерация картинки повторяется с растущими паузами (бесплатные
    # провайдеры часто отвечают 500). В тестах эти паузы означали бы 20 секунд
    # ожидания на каждый сбойный кейс — оставляем одну попытку без пауз.
    monkeypatch.setattr("app.image_generator._RETRY_PAUSES", (0,), raising=False)


# База в тестах одна на весь прогон (StaticPool + :memory:), и данные из
# предыдущего теста в ней остаются. Из-за этого фикстура test_user со вторым
# теста падала на уникальном email. Чистим таблицы перед каждым тестом.
# Сначала words: у них внешний ключ на users.
@pytest.fixture(autouse=True)
def clean_db():
    db = TestingSessionLocal()
    try:
        # Порядок важен: сначала таблицы со ссылками, потом те, на кого ссылаются.
        db.query(models.ReviewLog).delete()
        db.query(models.Word).delete()
        db.query(models.User).delete()
        db.execute(models.catalog_word_categories.delete())
        db.query(models.CatalogWord).delete()
        db.query(models.Category).delete()
        db.commit()
    finally:
        db.close()
    yield


# Синхронная обёртка для async-функций CRUD (create_word и др.).
# Позволяет обойтись без плагина pytest-asyncio в обычных тестах.
def run_async(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# Фикстура для тестового клиента. Подмена get_db уже стоит глобально (см. выше),
# поэтому здесь достаточно отдать клиента.
@pytest.fixture(scope="module")
def client():
    yield TestClient(app)

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