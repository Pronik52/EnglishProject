import logging
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi import APIRouter
from .routers import (
    auth as auth_router,
    words as words_router,
    billing as billing_router,
    catalog as catalog_router,
)
from .exceptions import validation_exception_handler, http_exception_handler
from .database import Base, engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="English Learning API")

# Создаём таблицы, которых ещё нет — только для SQLite (локальный запуск/демо),
# чтобы стартовать без миграций. На PostgreSQL схемой управляет Alembic, а
# подключение к нему при импорте здесь не нужно (иначе ломается сбор тестов).
if engine.dialect.name == "sqlite":
    Base.metadata.create_all(bind=engine)

    # create_all не добавляет новые колонки в уже существующие таблицы,
    # поэтому для локальной SQLite-базы дозагружаем недостающие вручную.
    from sqlalchemy import text, inspect
    _cols = {c["name"] for c in inspect(engine).get_columns("users")}
    if "level" not in _cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN level VARCHAR NOT NULL DEFAULT 'A1'"))
    if "is_premium" not in _cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_premium BOOLEAN NOT NULL DEFAULT 0"))
    if "premium_until" not in _cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN premium_until DATETIME"))

    _word_cols = {c["name"] for c in inspect(engine).get_columns("words")}
    if "regen_count" not in _word_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN regen_count INTEGER NOT NULL DEFAULT 0"))
    if "phrase_ru" not in _word_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN phrase_ru VARCHAR"))
    if "srs_level" not in _word_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN srs_level INTEGER NOT NULL DEFAULT 0"))
    if "due_at" not in _word_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN due_at DATETIME"))
    if "scene_prompt" not in _word_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN scene_prompt VARCHAR"))
    if "image_url" not in _word_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN image_url VARCHAR"))
    if "image_status" not in _word_cols:
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE words ADD COLUMN image_status VARCHAR NOT NULL DEFAULT 'none'"
            ))
    if "catalog_word_id" not in _word_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE words ADD COLUMN catalog_word_id INTEGER"))

    # Индексы для уже существующей таблицы words: create_all создаёт их только
    # вместе с самой таблицей. IF NOT EXISTS вместо проверки через inspect —
    # рефлексия SQLAlchemy не видит индексы по выражению (lower(...)) и на
    # каждом старте пыталась бы создать уникальный ключ заново.
    for _sql in (
        "CREATE INDEX IF NOT EXISTS ix_words_owner_id ON words (owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_words_catalog_word_id ON words (catalog_word_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_words_owner_word_meaning "
        "ON words (owner_id, lower(text), lower(translation))",
    ):
        try:
            with engine.begin() as conn:
                conn.execute(text(_sql))
        except Exception as e:
            # Уникальный ключ не встанет, если в базе уже есть дубли. Приложение
            # из-за этого падать не должно: дублями занимается миграция
            # d9b31c7a0e46, которая говорит, что именно чинить.
            logging.getLogger(__name__).warning("Индекс словаря не создан: %s", e)

# Глобальный обработчик ошибок
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url}")
    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        raise
    logger.info(f"Request completed: {response.status_code}")
    return response

# Версионирование API
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router.router, prefix="/auth")
api_router.include_router(words_router.router)
api_router.include_router(billing_router.router)
api_router.include_router(catalog_router.router)

app.include_router(api_router)

from fastapi.responses import RedirectResponse

# Отдаём минимальный фронтенд (SPA в одном файле) по адресу /app.
_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")

# Сгенерированные картинки-сцены отдаём как обычную статику по /media.
# Каталог создаём заранее: StaticFiles падает при монтировании, если его нет.
# На бою эту раздачу лучше забрать себе Caddy — он сделает это быстрее.
from .image_generator import SCENES_DIR, MEDIA_ROOT

SCENES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")


@app.get("/")
def root():
    # С корня отправляем пользователя сразу в веб-интерфейс.
    return RedirectResponse(url="/app/")

# Редиректы для обратной совместимости
@app.post("/login")
def redirect_login():
    return RedirectResponse(url="/api/v1/auth/login", status_code=307)

@app.post("/register")
def redirect_register():
    return RedirectResponse(url="/api/v1/auth/register", status_code=307)

@app.get("/me")
def redirect_me():
    return RedirectResponse(url="/api/v1/auth/me", status_code=307)
