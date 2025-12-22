"""add_activity_time_slots_view

Revision ID: 2308848b6589
Revises: b22b6e46cac7
Create Date: 2025-12-22 20:52:19.445155

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2308848b6589'
down_revision: Union[str, Sequence[str], None] = 'b22b6e46cac7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
    CREATE OR REPLACE VIEW v_activity_time_slots AS
    SELECT 
        response_id,
        survey_id,
        started_at as full_timestamp,
        -- Извлекаем час (0-23)
        EXTRACT(HOUR FROM started_at)::INT as hour_of_day,
        -- Извлекаем день недели (1 - Пн, 7 - Вс)
        EXTRACT(ISODOW FROM started_at)::INT as day_of_week,
        -- Форматируем название дня для отладки
        TO_CHAR(started_at, 'Dy') as day_name
    FROM survey_responses;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW IF EXISTS v_activity_time_slots;")
