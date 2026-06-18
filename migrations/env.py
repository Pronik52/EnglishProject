import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv

# Загружаем .env — чтобы получить DATABASE_URL
load_dotenv()

# Стандартная настройка логов Alembic (из alembic.ini)
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# КЛЮЧЕВАЯ СТРОКА: говорим Alembic, где искать модели.
# Base.metadata содержит описание всех таблиц — Alembic сравнивает
# его с реальной БД и генерирует нужные изменения.
from app.models import Base
target_metadata = Base.metadata

# Берём URL из .env — не дублируем пароль в alembic.ini.
# Переопределяем то, что написано в alembic.ini.
db_url = os.getenv("DATABASE_URL")
config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline() -> None:
    """Режим offline: генерирует SQL-скрипт без подключения к БД."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Режим online: подключается к БД и применяет миграции напрямую."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()