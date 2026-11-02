"""estacao: estacao_leitura (sensor de teste)

Revision ID: estacao_0001
Revises:
Create Date: 2026-11-01
"""
import sqlalchemy as sa
from alembic import op

revision = "estacao_0001"
down_revision = None
branch_labels = ("estacao",)
depends_on = "nucleo_0001"


def upgrade() -> None:
    op.create_table(
        "estacao_leitura",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipamento_id", sa.Integer(), nullable=False),
        sa.Column("envio_id", sa.Integer(), nullable=False),
        sa.Column("tempo", sa.DateTime(), nullable=False),
        sa.Column("arquivo", sa.String(length=64), nullable=False),
        sa.Column("corrompido", sa.Boolean(), nullable=False),
        sa.Column("chuva", sa.Float(), nullable=True, comment="mm/h"),
        sa.Column("temperatura", sa.Float(), nullable=True, comment="graus Celsius"),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("tensao", sa.Float(), nullable=True, comment="V"),
        sa.Column("intervalo", sa.Integer(), nullable=True, comment="s"),
        sa.Column("numero_serie", sa.String(length=32), nullable=True),
        sa.Column("firmware", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["equipamento_id"], ["equipamento.id"],
                                name=op.f("fk_estacao_leitura_equipamento_id_equipamento")),
        sa.ForeignKeyConstraint(["envio_id"], ["envio.id"], name=op.f("fk_estacao_leitura_envio_id_envio")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_estacao_leitura")),
        sa.UniqueConstraint("equipamento_id", "tempo", name=op.f("uq_estacao_leitura_equipamento_id_tempo")),
    )
    op.create_index(op.f("ix_estacao_leitura_envio_id"), "estacao_leitura", ["envio_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_estacao_leitura_envio_id"), table_name="estacao_leitura")
    op.drop_table("estacao_leitura")
