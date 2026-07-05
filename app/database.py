import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Загружаем переменные из файла .env в окружение программы.
load_dotenv()

# Читаем строку подключения, которую положили в .env.
DATABASE_URL = os.getenv("DATABASE_URL")

# Engine — "двигатель", низкоуровневое соединение с базой.
# Для SQLite (локальный запуск/демо без PostgreSQL) нужен особый флаг
# check_same_thread=False, иначе SQLAlchemy ругается в многопоточном FastAPI.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

# SessionLocal — "фабрика сессий".
# Сессия = одна рабочая единица общения с базой (как транзакция/контекст).
# autocommit=False, autoflush=False — стандартные безопасные настройки:
#   мы сами решаем, когда фиксировать изменения через commit().
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base — базовый класс, от которого будут наследоваться ВСЕ наши модели (таблицы).
# SQLAlchemy через него ведёт реестр всех таблиц.
Base = declarative_base()

# Единая точка получения сессии БД. Импортируется везде, где нужна база.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()