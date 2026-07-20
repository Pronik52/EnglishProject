"""журнал повторов (review_logs)

Revision ID: b7e2d1840c93
Revises: a3f1c9d24b70
Create Date: 2026-07-20 17:05:00.000000

Одна запись на каждый ответ пользователя. Счётчики в words хранят только итог,
а история нужна для статистики, графиков прогресса и дневных лимитов — из
review_count её восстановить нельзя, поэтому пишем сразу.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'b7e2d1840c93'
down_revision: Union[str, Sequence[str], None] = 'a3f1c9d24b70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    if "review_logs" in inspect(op.get_bind()).get_table_names():
        return

    op.create_table(
        "review_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answer_text", sa.String(), nullable=True),
        sa.Column("srs_level_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["word_id"], ["words.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # Индексы под то, как таблицу реально читают: «сколько ответов у этого
    # пользователя за сегодня» и «история по конкретному слову».
    op.create_index("ix_review_logs_user_id", "review_logs", ["user_id"])
    op.create_index("ix_review_logs_word_id", "review_logs", ["word_id"])
    op.create_index("ix_review_logs_created_at", "review_logs", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_review_logs_created_at", table_name="review_logs")
    op.drop_index("ix_review_logs_word_id", table_name="review_logs")
    op.drop_index("ix_review_logs_user_id", table_name="review_logs")
    op.drop_table("review_logs")
