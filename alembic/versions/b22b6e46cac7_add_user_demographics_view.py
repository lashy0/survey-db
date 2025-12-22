"""add_user_demographics_view

Revision ID: b22b6e46cac7
Revises: b8c42e06244a
Create Date: 2025-12-22 20:49:18.946721

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b22b6e46cac7'
down_revision: Union[str, Sequence[str], None] = 'b8c42e06244a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
    CREATE OR REPLACE VIEW v_user_demographics AS
    SELECT 
        u.user_id,
        u.full_name,
        -- Расчет точного возраста (лет)
        EXTRACT(YEAR FROM AGE(u.birth_date)) as exact_age,
        -- Категоризация
        CASE 
            WHEN u.birth_date IS NULL THEN 'Не указано'
            WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) < 18 THEN 'До 18'
            WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) BETWEEN 18 AND 24 THEN '18-24'
            WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) BETWEEN 25 AND 34 THEN '25-34'
            WHEN EXTRACT(YEAR FROM AGE(u.birth_date)) BETWEEN 35 AND 44 THEN '35-44'
            ELSE '45+'
        END AS age_group
    FROM users u;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW IF EXISTS v_user_demographics;")
