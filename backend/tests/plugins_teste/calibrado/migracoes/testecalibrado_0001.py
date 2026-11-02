"""testecalibrado: teste_calibrado_leitura

Revision ID: testecalibrado_0001
"""
import sqlalchemy as sa
from alembic import op

revision = "testecalibrado_0001"
down_revision = None
branch_labels = ("testecalibrado",)
depends_on = "nucleo_0001"


def upgrade() -> None:
    op.create_table(
        "teste_calibrado_leitura",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipamento_id", sa.Integer(), nullable=False),
        sa.Column("envio_id", sa.Integer(), nullable=False),
        sa.Column("tempo", sa.DateTime(), nullable=False),
        sa.Column("bruto", sa.Integer(), nullable=False),
        sa.Column("valor", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["equipamento_id"], ["equipamento.id"],
                                name=op.f("fk_teste_calibrado_leitura_equipamento_id_equipamento")),
        sa.ForeignKeyConstraint(["envio_id"], ["envio.id"], name=op.f("fk_teste_calibrado_leitura_envio_id_envio")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teste_calibrado_leitura")),
        sa.UniqueConstraint("equipamento_id", "tempo",
                            name=op.f("uq_teste_calibrado_leitura_equipamento_id_tempo")),
    )


def downgrade() -> None:
    op.drop_table("teste_calibrado_leitura")
