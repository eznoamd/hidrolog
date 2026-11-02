"""nucleo: regras de qualidade (regra_config) e ocorrencias

Revision ID: nucleo_0004
Revises: nucleo_0003
Create Date: 2026-10-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "nucleo_0004"
down_revision: Union[str, Sequence[str], None] = "nucleo_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "regra_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipamento_id", sa.Integer(), nullable=False),
        sa.Column("codigo_regra", sa.Text(), nullable=False),
        sa.Column("parametros", sa.JSON(), nullable=True, comment="so os que mudam do padrao da regra"),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.Column("alterada_por", sa.Integer(), nullable=True),
        sa.Column("alterada_em", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["equipamento_id"], ["equipamento.id"],
                                name=op.f("fk_regra_config_equipamento_id_equipamento")),
        sa.ForeignKeyConstraint(["alterada_por"], ["usuario.id"], name=op.f("fk_regra_config_alterada_por_usuario")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_regra_config")),
        sa.UniqueConstraint("equipamento_id", "codigo_regra", name=op.f("uq_regra_config_equipamento_id_codigo_regra")),
    )
    op.create_table(
        "ocorrencia",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipamento_id", sa.Integer(), nullable=False),
        sa.Column("envio_id", sa.Integer(), nullable=True),
        sa.Column("tempo", sa.DateTime(), nullable=True, comment="leitura (nivel leitura) ou instante do problema"),
        sa.Column("codigo_regra", sa.Text(), nullable=False),
        sa.Column("nivel", sa.Text(), nullable=False, comment="leitura, envio ou equipamento"),
        sa.Column("severidade", sa.Text(), nullable=False, comment="aviso, suspeita ou alerta"),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("criada_em", sa.DateTime(), nullable=False),
        sa.Column("resolvida_por", sa.Integer(), nullable=True),
        sa.Column("resolvida_em", sa.DateTime(), nullable=True,
                  comment="resolvida (resolvida_por nulo = a condicao deixou de valer)"),
        sa.ForeignKeyConstraint(["equipamento_id"], ["equipamento.id"],
                                name=op.f("fk_ocorrencia_equipamento_id_equipamento")),
        sa.ForeignKeyConstraint(["envio_id"], ["envio.id"], name=op.f("fk_ocorrencia_envio_id_envio")),
        sa.ForeignKeyConstraint(["resolvida_por"], ["usuario.id"], name=op.f("fk_ocorrencia_resolvida_por_usuario")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ocorrencia")),
    )
    op.create_index("ix_ocorrencia_equipamento_tempo", "ocorrencia", ["equipamento_id", "tempo"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ocorrencia_equipamento_tempo", table_name="ocorrencia")
    op.drop_table("ocorrencia")
    op.drop_table("regra_config")
