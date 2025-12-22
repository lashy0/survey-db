"""add_anomaly_candidates_view

Revision ID: b8c42e06244a
Revises: e38fc5fa1c13
Create Date: 2025-12-22 20:20:23.694673

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c42e06244a'
down_revision: Union[str, Sequence[str], None] = 'e38fc5fa1c13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
    CREATE OR REPLACE VIEW v_anomaly_candidates AS
    WITH survey_stats AS (
        -- Считаем среднее время прохождения для каждого опроса (в секундах)
        SELECT 
            survey_id, 
            AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_sec
        FROM survey_responses 
        WHERE completed_at IS NOT NULL
        GROUP BY survey_id
    )
    SELECT 
        sr.response_id,
        s.survey_id,
        s.title AS survey_title,
        u.full_name AS user_name,
        u.email AS user_email,
        EXTRACT(EPOCH FROM (sr.completed_at - sr.started_at)) AS user_duration_sec,
        ss.avg_sec AS survey_avg_sec,
        -- Отношение времени юзера к среднему времени (0.2 = в 5 раз быстрее среднего)
        ROUND((EXTRACT(EPOCH FROM (sr.completed_at - sr.started_at)) / NULLIF(ss.avg_sec, 0))::numeric, 3) AS speed_ratio
    FROM survey_responses sr
    JOIN surveys s ON sr.survey_id = s.survey_id
    JOIN users u ON sr.user_id = u.user_id
    JOIN survey_stats ss ON sr.survey_id = ss.survey_id
    WHERE sr.completed_at IS NOT NULL;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW IF EXISTS v_anomaly_candidates;")
