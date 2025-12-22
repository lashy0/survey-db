"""add_admin_summary_view

Revision ID: e6de686bc831
Revises: 5a518033839a
Create Date: 2025-12-22 20:03:25.739275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6de686bc831'
down_revision: Union[str, Sequence[str], None] = '5a518033839a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
    CREATE OR REPLACE VIEW v_admin_summary AS
    SELECT
        (SELECT COUNT(*) FROM users) AS total_users,
        (SELECT COUNT(*) FROM surveys) AS total_surveys,
        (SELECT COUNT(*) FROM survey_responses) AS total_responses,
        (SELECT COUNT(*) FROM survey_responses WHERE completed_at IS NOT NULL) AS total_completed_responses,
        (SELECT COUNT(*) FROM tags) AS total_tags;
    """)



def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP VIEW IF EXISTS v_admin_summary;")
