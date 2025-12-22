"""fix_admin_summary_funnel_logic

Revision ID: e38fc5fa1c13
Revises: e6de686bc831
Create Date: 2025-12-22 20:08:47.163386

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e38fc5fa1c13'
down_revision: Union[str, Sequence[str], None] = 'e6de686bc831'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP VIEW IF EXISTS v_admin_summary;")
    
    op.execute("""
    CREATE OR REPLACE VIEW v_admin_summary AS
    SELECT
        -- 1. Всего зарегистрированных людей
        (SELECT COUNT(*) FROM users) AS total_users,
        
        -- 2. Уникальные пользователи, которые начали хотя бы 1 опрос
        (SELECT COUNT(DISTINCT user_id) FROM survey_responses) AS unique_users_started,
        
        -- 3. Уникальные пользователи, которые завершили хотя бы 1 опрос
        (SELECT COUNT(DISTINCT user_id) FROM survey_responses WHERE completed_at IS NOT NULL) AS unique_users_completed,
        
        (SELECT COUNT(*) FROM surveys) AS total_surveys,
        (SELECT COUNT(*) FROM survey_responses) AS total_responses_sessions;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    pass
