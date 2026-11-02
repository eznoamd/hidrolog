"""nucleo: plugin_instalado e auditoria_plugin (gerenciador de plugins)

Revision ID: nucleo_0002
Revises: nucleo_0001
Create Date: 2026-10-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "nucleo_0002"
down_revision: Union[str, Sequence[str], None] = "nucleo_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plugin_instalado",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.Text(), nullable=False),
        sa.Column("nome", sa.Text(), nullable=False),
        sa.Column("versao", sa.Text(), nullable=False),
        sa.Column("contrato", sa.Text(), nullable=False, comment="versao do contrato declarada, ex. 1.x"),
        sa.Column("origem", sa.Text(), nullable=False, comment="interno, pasta, zip ou github"),
        sa.Column("url", sa.Text(), nullable=True, comment="github: URL do repositorio"),
        sa.Column("tag", sa.Text(), nullable=True, comment="github: tag ou release"),
        sa.Column("sha256", sa.Text(), nullable=True, comment="hash do pacote importado"),
        sa.Column("caminho", sa.Text(), nullable=True),
        sa.Column("instalado_por", sa.Integer(), nullable=True),
        sa.Column("instalado_em", sa.DateTime(), nullable=False),
        sa.Column("situacao", sa.Text(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["instalado_por"], ["usuario.id"],
                                name=op.f("fk_plugin_instalado_instalado_por_usuario")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plugin_instalado")),
        sa.UniqueConstraint("codigo", "versao", name=op.f("uq_plugin_instalado_codigo_versao")),
    )
    op.create_index(op.f("ix_plugin_instalado_codigo"), "plugin_instalado", ["codigo"], unique=False)
    op.create_table(
        "auditoria_plugin",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quando", sa.DateTime(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("login", sa.Text(), nullable=False,
                  comment="quem (copia do login, fica mesmo se o usuario mudar)"),
        sa.Column("acao", sa.Text(), nullable=False, comment="importar, atualizar, desativar, reativar, "
                                                              "voltar_versao, remover, migrar, senha"),
        sa.Column("codigo", sa.Text(), nullable=True),
        sa.Column("versao", sa.Text(), nullable=True),
        sa.Column("origem", sa.Text(), nullable=True),
        sa.Column("resultado", sa.Text(), nullable=False, comment="ok, recusado, cancelado ou erro"),
        sa.Column("detalhes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], name=op.f("fk_auditoria_plugin_usuario_id_usuario")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auditoria_plugin")),
    )
    op.create_index(op.f("ix_auditoria_plugin_quando"), "auditoria_plugin", ["quando"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_auditoria_plugin_quando"), table_name="auditoria_plugin")
    op.drop_table("auditoria_plugin")
    op.drop_index(op.f("ix_plugin_instalado_codigo"), table_name="plugin_instalado")
    op.drop_table("plugin_instalado")
