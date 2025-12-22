"""add_survey_benchmark_function

Revision ID: 49e99ca29ac9
Revises: 540fa1a9b90f
Create Date: 2025-12-22 18:56:53.080109

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '49e99ca29ac9'
down_revision: Union[str, Sequence[str], None] = '540fa1a9b90f'
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
        -- 1. Получаем список всех тегов текущего опроса
        SELECT array_agg(tag_id) INTO v_tag_ids FROM survey_tags WHERE survey_id = p_survey_id;

        RETURN QUERY
        WITH category_surveys AS (
            -- Находим все опросы в этой же категории (по тегам)
            SELECT DISTINCT st.survey_id
            FROM survey_tags st
            WHERE st.tag_id = ANY(v_tag_ids)
        ),
        category_metrics AS (
            -- Считаем метрики для всей категории
            SELECT 
                sr.survey_id,
                COUNT(*)::NUMERIC as resp_count,
                AVG(EXTRACT(EPOCH FROM (sr.completed_at - sr.started_at)))::NUMERIC as avg_dur
            FROM survey_responses sr
            WHERE sr.survey_id IN (SELECT survey_id FROM category_surveys)
              AND sr.completed_at IS NOT NULL
            GROUP BY sr.survey_id
        )
        -- Формируем итоговую таблицу сравнения
        SELECT 
            'Количество ответов'::TEXT,
            (SELECT count(*)::NUMERIC FROM survey_responses WHERE survey_id = p_survey_id),
            ROUND(AVG(resp_count), 1)
        FROM category_metrics
        UNION ALL
        SELECT 
            'Среднее время прохождения (сек)'::TEXT,
            COALESCE((SELECT AVG(EXTRACT(EPOCH FROM (completed_at - started_at)))::NUMERIC 
             FROM survey_responses WHERE survey_id = p_survey_id AND completed_at IS NOT NULL), 0),
            ROUND(AVG(avg_dur), 1)
        FROM category_metrics;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP FUNCTION IF EXISTS get_survey_benchmark(INT);")
