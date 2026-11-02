"""nucleo: ficha do equipamento (coordenadas, instalacao, atributos do plugin)

Revision ID: nucleo_0003
Revises: nucleo_0002
Create Date: 2026-10-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "nucleo_0003"
down_revision: Union[str, Sequence[str], None] = "nucleo_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("equipamento") as tabela:
        tabela.add_column(sa.Column("latitude", sa.Float(), nullable=True, comment="graus decimais, WGS84"))
        tabela.add_column(sa.Column("longitude", sa.Float(), nullable=True, comment="graus decimais, WGS84"))
        tabela.add_column(sa.Column("altitude_m", sa.Float(), nullable=True, comment="metros acima do nivel do mar"))
        tabela.add_column(sa.Column("instalado_em", sa.Date(), nullable=True))
        tabela.add_column(sa.Column("atributos", sa.JSON(), nullable=True,
                                    comment="ficha do plugin (validada por ele): {campo: valor}"))
        tabela.add_column(sa.Column("versao_ficha", sa.Integer(), nullable=True,
                                    comment="versao da ficha do plugin quando os atributos foram gravados"))


def downgrade() -> None:
    with op.batch_alter_table("equipamento") as tabela:
        for coluna in ("versao_ficha", "atributos", "instalado_em", "altitude_m", "longitude", "latitude"):
            tabela.drop_column(coluna)
