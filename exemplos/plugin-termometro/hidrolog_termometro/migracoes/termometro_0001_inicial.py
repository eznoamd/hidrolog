"""termometro: termometro_leitura

Revision ID: termometro_0001
Revises:
Create Date: 2026-10-30
"""
import sqlalchemy as sa
from alembic import op

revision = "termometro_0001"
down_revision = None
branch_labels = ("termometro",)
depends_on = "nucleo_0001"


def upgrade() -> None:
    op.create_table(
        "termometro_leitura",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipamento_id", sa.Integer(), nullable=False),
        sa.Column("envio_id", sa.Integer(), nullable=False),
        sa.Column("tempo", sa.DateTime(), nullable=False),
        sa.Column("temperatura", sa.Float(), nullable=True, comment="graus Celsius"),
        sa.ForeignKeyConstraint(["equipamento_id"], ["equipamento.id"],
                                name=op.f("fk_termometro_leitura_equipamento_id_equipamento")),
        sa.ForeignKeyConstraint(["envio_id"], ["envio.id"], name=op.f("fk_termometro_leitura_envio_id_envio")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_termometro_leitura")),
        sa.UniqueConstraint("equipamento_id", "tempo", name=op.f("uq_termometro_leitura_equipamento_id_tempo")),
    )
    op.create_index(op.f("ix_termometro_leitura_envio_id"), "termometro_leitura", ["envio_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_termometro_leitura_envio_id"), table_name="termometro_leitura")
    op.drop_table("termometro_leitura")
