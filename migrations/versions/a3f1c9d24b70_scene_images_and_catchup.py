"""scene images + догоняем колонки, добавленные в модели без миграций

Revision ID: a3f1c9d24b70
Revises: 1605fb67e5d5
Create Date: 2026-07-20 16:10:00.000000

Миграция делает две вещи.

1. Добавляет поля картинки-сцены: scene_prompt, image_url, image_status.

2. Догоняет схему. Колонки level/is_premium/premium_until у users и
   phrase/phrase_ru/srs_level/due_at/regen_count у words появились в
   app/models.py, но миграций для них никто не создал: локально их дописывал
   вручную блок автопочинки SQLite в app/main.py, и расхождение не было
   заметно. На чистой PostgreSQL `alembic upgrade head` собрал бы схему без
   этих колонок, и приложение упало бы на первом же запросе.

Каждое добавление проверяется через inspector: базы, которые уже правились
руками, переживут миграцию без ошибки «column already exists».
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'a3f1c9d24b70'
down_revision: Union[str, Sequence[str], None] = '1605fb67e5d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Что должно быть в схеме: таблица -> список колонок.
_COLUMNS = {
    "users": [
        sa.Column("level", sa.String(), nullable=False, server_default="A1"),
        sa.Column("is_premium", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("premium_until", sa.DateTime(timezone=True), nullable=True),
    ],
    "words": [
        sa.Column("phrase", sa.String(), nullable=True),
        sa.Column("phrase_ru", sa.String(), nullable=True),
        sa.Column("srs_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("regen_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scene_prompt", sa.String(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("image_status", sa.String(), nullable=False, server_default="none"),
    ],
}


def _existing(table: str) -> set[str]:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    """Upgrade schema."""
    for table, columns in _COLUMNS.items():
        present = _existing(table)
        for column in columns:
            if column.name not in present:
                op.add_column(table, column)


def downgrade() -> None:
    """Downgrade schema.

    Откатываем ТОЛЬКО поля картинки. Остальные колонки этой миграции старше её
    самой и нужны работающему приложению — их удаление сломало бы код,
    который уже давно на них рассчитывает.
    """
    present = _existing("words")
    for name in ("image_status", "image_url", "scene_prompt"):
        if name in present:
            op.drop_column("words", name)
