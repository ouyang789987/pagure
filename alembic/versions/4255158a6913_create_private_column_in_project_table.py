"""Create private column in project table

Revision ID: 4255158a6913
Revises: 317a285e04a8
Create Date: 2016-06-06 14:33:47.039207

"""

# revision identifiers, used by Alembic.
revision = '4255158a6913'
down_revision = '317a285e04a8'

from alembic import op
import sqlalchemy as sa


def upgrade():
    ''' Add a pivate column in the project table
    '''
    op.add_column(
        'projects',
        sa.Column('private', sa.Boolean, nullable=False, default=False)
    )



def downgrade():
    ''' Remove the private column
    '''
    op.drop_column('projects', 'private')
