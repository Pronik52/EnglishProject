"""уникальность и индексы личного словаря

Revision ID: d9b31c7a0e46
Revises: c4a8e91f3d25
Create Date: 2026-07-20 18:35:00.000000

До этой миграции у words не было ни одного ограничения уникальности: одно и то
же слово можно было завести дважды, а параллельные запросы могли создать дубль
в обход проверок в коде.

Ключ включает ПЕРЕВОД, а не только само слово: book/книга и book/бронировать —
две разные учебные единицы, и запрещать вторую нельзя. lower() приводит
«Book» и «book» к одному ключу.

Миграция не удаляет данные. Если дубли уже накопились, она останавливается с
понятным сообщением: решать, какую из записей оставить, должен человек, а не
автоматика.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'd9b31c7a0e46'
down_revision: Union[str, Sequence[str], None] = 'c4a8e91f3d25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UNIQUE_INDEX = "uq_words_owner_word_meaning"
_OWNER_INDEX = "ix_words_owner_id"


def _indexes() -> set:
    return {i["name"] for i in inspect(op.get_bind()).get_indexes("words")}


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    duplicates = bind.execute(sa.text("""
        SELECT owner_id, lower(text) AS w, lower(translation) AS t, COUNT(*) AS n
        FROM words
        GROUP BY owner_id, lower(text), lower(translation)
        HAVING COUNT(*) > 1
    """)).fetchall()

    if duplicates:
        preview = ", ".join(f"пользователь {d[0]}: {d[1]}/{d[2]} ({d[3]} шт.)"
                            for d in duplicates[:5])
        raise RuntimeError(
            f"В таблице words есть дубли, уникальный ключ создать нельзя. "
            f"Групп с дублями: {len(duplicates)}. Примеры — {preview}. "
            f"Удалите лишние записи (обычно оставляют самую раннюю по created_at) "
            f"и повторите миграцию."
        )

    existing = _indexes()
    if _UNIQUE_INDEX not in existing:
        op.create_index(_UNIQUE_INDEX, "words",
                        ["owner_id", sa.text("lower(text)"), sa.text("lower(translation)")],
                        unique=True)
    if _OWNER_INDEX not in existing:
        op.create_index(_OWNER_INDEX, "words", ["owner_id"])


def downgrade() -> None:
    """Downgrade schema."""
    existing = _indexes()
    if _UNIQUE_INDEX in existing:
        op.drop_index(_UNIQUE_INDEX, table_name="words")
    if _OWNER_INDEX in existing:
        op.drop_index(_OWNER_INDEX, table_name="words")
