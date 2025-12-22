"""fix_benchmark_empty_result_final

Revision ID: 05ccf504dc51
Revises: 7b3724d89faa
Create Date: 2025-12-22 19:08:56.247300

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '05ccf504dc51'
down_revision: Union[str, Sequence[str], None] = '7b3724d89faa'
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
        -- 1. Получаем теги текущего опроса
        SELECT array_agg(tag_id) INTO v_tag_ids FROM survey_tags WHERE survey_id = p_survey_id;

        RETURN QUERY
        WITH category_surveys AS (
            SELECT DISTINCT st.survey_id FROM survey_tags st WHERE st.tag_id = ANY(v_tag_ids)
        ),
        category_metrics AS (
            SELECT 
                sr.survey_id,
                COUNT(*)::NUMERIC as resp_count,
                AVG(EXTRACT(EPOCH FROM (sr.completed_at - sr.started_at)))::NUMERIC as avg_dur
            FROM survey_responses sr
            WHERE sr.survey_id IN (SELECT survey_id FROM category_surveys)
              AND sr.completed_at IS NOT NULL
            GROUP BY sr.survey_id
        )
        -- ВАЖНО: Убираем FROM category_metrics из основного селекта, чтобы строки возвращались всегда
        SELECT 
            'Количество ответов'::TEXT,
            COALESCE((SELECT count(*)::NUMERIC FROM survey_responses WHERE survey_id = p_survey_id), 0),
            COALESCE((SELECT ROUND(AVG(resp_count), 1) FROM category_metrics), 0)
        UNION ALL
        SELECT 
            'Среднее время (сек)'::TEXT,
            COALESCE((SELECT AVG(EXTRACT(EPOCH FROM (completed_at - started_at)))::NUMERIC 
             FROM survey_responses WHERE survey_id = p_survey_id AND completed_at IS NOT NULL), 0),
            COALESCE((SELECT ROUND(AVG(avg_dur), 1) FROM category_metrics), 0);
    END;
    $$ LANGUAGE plpgsql;
    """)



def downgrade() -> None:
    """Downgrade schema."""
    pass
