"""каталог готовых слов: категории, каталожные слова, связь с личным словарём

Revision ID: c4a8e91f3d25
Revises: b7e2d1840c93
Create Date: 2026-07-20 18:20:00.000000

Каталог отделён от пользовательского словаря: categories и catalog_words
общие для всех, а у words появляется необязательная ссылка catalog_word_id
на источник. Существующие слова не трогаются — у них ссылка остаётся NULL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'c4a8e91f3d25'
down_revision: Union[str, Sequence[str], None] = 'b7e2d1840c93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set:
    return set(inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    """Upgrade schema."""
    tables = _tables()

    if "categories" not in tables:
        op.create_table(
            "categories",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("slug", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
        )
        op.create_index("ix_categories_slug", "categories", ["slug"])

    if "catalog_words" not in tables:
        op.create_table(
            "catalog_words",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("text", sa.String(), nullable=False),
            sa.Column("translation", sa.String(), nullable=False),
            sa.Column("part_of_speech", sa.String(), nullable=True),
            sa.Column("level", sa.String(), nullable=False),
            sa.Column("transcription", sa.String(), nullable=True),
            sa.Column("example_en", sa.String(), nullable=True),
            sa.Column("example_ru", sa.String(), nullable=True),
            sa.Column("frequency_rank", sa.Integer(), nullable=False, server_default="1000"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_catalog_words_level", "catalog_words", ["level"])
        op.create_index("ix_catalog_words_level_active", "catalog_words", ["level", "is_active"])
        op.create_index("ix_catalog_words_frequency", "catalog_words", ["frequency_rank"])
        # Уникальность на уровне ЗНАЧЕНИЯ: book/книга и book/бронировать —
        # две разные записи, а вот второй раз book/книга завести нельзя.
        op.create_index("uq_catalog_word_meaning", "catalog_words",
                        [sa.text("lower(text)"), sa.text("lower(translation)")], unique=True)

    if "catalog_word_categories" not in tables:
        op.create_table(
            "catalog_word_categories",
            sa.Column("catalog_word_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["catalog_word_id"], ["catalog_words.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("catalog_word_id", "category_id"),
        )

    if "catalog_word_id" not in _columns("words"):
        op.add_column("words", sa.Column("catalog_word_id", sa.Integer(), nullable=True))
        op.create_index("ix_words_catalog_word_id", "words", ["catalog_word_id"])
        # Внешний ключ добавляем отдельно: SQLite не умеет ALTER TABLE ADD
        # CONSTRAINT, и там связь остаётся логической. На PostgreSQL — настоящей.
        if op.get_bind().dialect.name != "sqlite":
            op.create_foreign_key("fk_words_catalog_word", "words",
                                  "catalog_words", ["catalog_word_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    if "catalog_word_id" in _columns("words"):
        if op.get_bind().dialect.name != "sqlite":
            op.drop_constraint("fk_words_catalog_word", "words", type_="foreignkey")
        op.drop_index("ix_words_catalog_word_id", table_name="words")
        op.drop_column("words", "catalog_word_id")

    tables = _tables()
    if "catalog_word_categories" in tables:
        op.drop_table("catalog_word_categories")
    if "catalog_words" in tables:
        op.drop_table("catalog_words")
    if "categories" in tables:
        op.drop_table("categories")
