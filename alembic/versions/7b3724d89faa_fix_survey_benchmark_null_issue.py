"""fix_survey_benchmark_null_issue

Revision ID: 7b3724d89faa
Revises: 49e99ca29ac9
Create Date: 2025-12-22 19:05:42.379097

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b3724d89faa'
down_revision: Union[str, Sequence[str], None] = '49e99ca29ac9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
    CREATE OR REPLACE FUNCTION get_survey_benchmark(p_survey_id INT)
    RETURNS TABLE (metric_name TEXT, survey_value NUMERIC, category_avg NUMERIC) AS $$
    DECLARE
        v_tag_ids INT[];
    BEGIN
        -- Получаем теги текущего опроса
        SELECT array_agg(tag_id) INTO v_tag_ids FROM survey_tags WHERE survey_id = p_survey_id;

        RETURN QUERY
        WITH category_surveys AS (
            SELECT DISTINCT st.survey_id FROM survey_tags st WHERE st.tag_id = ANY(v_tag_ids)
        ),
        category_metrics AS (
            -- Считаем метрики для всех опросов в этих категориях
            SELECT 
                sr.survey_id,
                COUNT(*)::NUMERIC as resp_count,
                AVG(EXTRACT(EPOCH FROM (sr.completed_at - sr.started_at)))::NUMERIC as avg_dur
            FROM survey_responses sr
            WHERE sr.survey_id IN (SELECT survey_id FROM category_surveys)
            GROUP BY sr.survey_id
        )
        SELECT 
            'Количество ответов'::TEXT,
            COALESCE((SELECT count(*)::NUMERIC FROM survey_responses WHERE survey_id = p_survey_id), 0),
            ROUND(COALESCE((SELECT AVG(resp_count) FROM category_metrics), 0), 1)
        UNION ALL
        SELECT 
            'Среднее время прохождения (сек)'::TEXT,
            COALESCE((SELECT AVG(EXTRACT(EPOCH FROM (completed_at - started_at)))::NUMERIC 
             FROM survey_responses WHERE survey_id = p_survey_id AND completed_at IS NOT NULL), 0),
            ROUND(COALESCE((SELECT AVG(avg_dur) FROM category_metrics), 0), 1);
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    pass
