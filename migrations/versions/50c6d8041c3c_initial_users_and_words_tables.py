"""initial: users and words tables

Revision ID: 50c6d8041c3c
Revises:
Create Date: 2026-06-18 12:54:34.057073

Миграцию автогенерировали на базе, где таблицы уже существовали, поэтому
Alembic не увидел разницы и оставил пустое тело. Из-за этого `alembic upgrade
head` на ЧИСТОЙ базе падал на следующей же ревизии с «no such table: words» —
то есть развернуть проект с нуля по миграциям было нельзя.

Тело восстановлено: таблицы создаются в том виде, какими они были на этот
момент истории. Колонки, добавленные позже (is_learned, level, is_premium,
phrase, srs_level и остальные), остаются за своими ревизиями.

Для баз, которые уже прошли эту ревизию, ничего не меняется: они отмечены
более поздней версией и повторно её не выполняют, а проверка ниже страхует
от повторного создания в любом случае.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '50c6d8041c3c'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    tables = set(inspect(op.get_bind()).get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("hashed_password", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_users_id", "users", ["id"])
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if "words" not in tables:
        op.create_table(
            "words",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("text", sa.String(), nullable=False),
            sa.Column("translation", sa.String(), nullable=False),
            sa.Column("review_count", sa.Integer(), server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("owner_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_words_id", "words", ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    tables = set(inspect(op.get_bind()).get_table_names())
    if "words" in tables:
        op.drop_table("words")
    if "users" in tables:
        op.drop_table("users")
