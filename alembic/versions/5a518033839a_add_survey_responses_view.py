"""add_survey_responses_view

Revision ID: 5a518033839a
Revises: 05ccf504dc51
Create Date: 2025-12-22 19:47:13.514051

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a518033839a'
down_revision: Union[str, Sequence[str], None] = '05ccf504dc51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
    CREATE OR REPLACE VIEW v_survey_responses_flat AS
    SELECT 
        ua.answer_id,
        s.survey_id,
        s.title AS survey_title,
        q.question_id,
        q.question_text,
        q.question_type,
        -- Собираем либо текст варианта, либо текст ответа в одну колонку для удобства
        COALESCE(o.option_text, ua.text_answer) AS answer_content,
        u.user_id,
        u.full_name AS respondent_name,
        -- Добавим возраст на момент прохождения (полезно для аналитики)
        EXTRACT(YEAR FROM AGE(u.birth_date)) AS respondent_age,
        sr.completed_at
    FROM user_answers ua
    JOIN questions q ON ua.question_id = q.question_id
    JOIN surveys s ON q.survey_id = s.survey_id
    JOIN survey_responses sr ON ua.response_id = sr.response_id
    LEFT JOIN options o ON ua.selected_option_id = o.option_id
    LEFT JOIN users u ON sr.user_id = u.user_id
    WHERE sr.completed_at IS NOT NULL;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW IF EXISTS v_survey_responses_flat;")
