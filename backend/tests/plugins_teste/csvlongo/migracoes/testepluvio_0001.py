"""testepluvio: teste_pluvio_leitura

Revision ID: testepluvio_0001
"""
import sqlalchemy as sa
from alembic import op

revision = "testepluvio_0001"
down_revision = None
branch_labels = ("testepluvio",)
depends_on = "nucleo_0001"


def upgrade() -> None:
    op.create_table(
        "teste_pluvio_leitura",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipamento_id", sa.Integer(), nullable=False),
        sa.Column("envio_id", sa.Integer(), nullable=False),
        sa.Column("tempo", sa.DateTime(), nullable=False),
        sa.Column("pulsos", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["equipamento_id"], ["equipamento.id"],
                                name=op.f("fk_teste_pluvio_leitura_equipamento_id_equipamento")),
        sa.ForeignKeyConstraint(["envio_id"], ["envio.id"], name=op.f("fk_teste_pluvio_leitura_envio_id_envio")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teste_pluvio_leitura")),
        sa.UniqueConstraint("equipamento_id", "tempo", name=op.f("uq_teste_pluvio_leitura_equipamento_id_tempo")),
    )


def downgrade() -> None:
    op.drop_table("teste_pluvio_leitura")
