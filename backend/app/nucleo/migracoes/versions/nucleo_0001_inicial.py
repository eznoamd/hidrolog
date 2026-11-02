"""nucleo: usuario, tipo_sensor, equipamento, envio

Revision ID: nucleo_0001
Revises:
Create Date: 2026-10-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "nucleo_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = ("nucleo",)
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('tipo_sensor',
    sa.Column('codigo', sa.Text(), nullable=False),
    sa.Column('nome', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('codigo', name=op.f('pk_tipo_sensor'))
    )
    op.create_table('usuario',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('login', sa.Text(), nullable=False),
    sa.Column('nome', sa.Text(), nullable=False),
    sa.Column('senha_hash', sa.Text(), nullable=False, comment='argon2id (argon2-cffi)'),
    sa.Column('perfil', sa.Text(), nullable=False, comment='master, cadastro ou leitura'),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_usuario')),
    sa.UniqueConstraint('login', name=op.f('uq_usuario_login'))
    )
    op.create_table('equipamento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo_sensor', sa.Text(), nullable=False),
    sa.Column('nome', sa.Text(), nullable=False),
    sa.Column('numero_serie', sa.Text(), nullable=True),
    sa.Column('local', sa.Text(), nullable=True),
    sa.Column('observacoes', sa.Text(), nullable=True),
    sa.Column('ativo', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['tipo_sensor'], ['tipo_sensor.codigo'], name=op.f('fk_equipamento_tipo_sensor_tipo_sensor')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_equipamento')),
    sa.UniqueConstraint('nome', name=op.f('uq_equipamento_nome'))
    )
    op.create_table('envio',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('equipamento_id', sa.Integer(), nullable=False),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('recebido_em', sa.DateTime(), nullable=False),
    sa.Column('canal', sa.Text(), nullable=False, comment='local ou upload'),
    sa.Column('tipo', sa.Text(), nullable=False, comment='zip, rar, pasta, arquivos ou misto'),
    sa.Column('origem', sa.Text(), nullable=False, comment='nome(s) do arquivo ou caminho'),
    sa.Column('arquivos_recebidos', sa.Integer(), nullable=False, comment='todos, inclusive ignorados'),
    sa.Column('ignorados', sa.Integer(), nullable=False, comment='arquivos que nao sao do sensor'),
    sa.Column('leituras', sa.Integer(), nullable=False, comment='arquivos de dados do sensor'),
    sa.Column('validas', sa.Integer(), nullable=False),
    sa.Column('corrompidas', sa.Integer(), nullable=False),
    sa.Column('novas', sa.Integer(), nullable=False, comment='inseridas (validas e corrompidas)'),
    sa.Column('duplicadas', sa.Integer(), nullable=False, comment='ja no banco ou repetidas no envio'),
    sa.Column('inicio', sa.DateTime(), nullable=True, comment='primeira leitura do envio'),
    sa.Column('fim', sa.DateTime(), nullable=True, comment='ultima leitura do envio'),
    sa.Column('duracao_s', sa.Float(), nullable=False, comment='tempo da importacao'),
    sa.Column('avisos', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['equipamento_id'], ['equipamento.id'], name=op.f('fk_envio_equipamento_id_equipamento')),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuario.id'], name=op.f('fk_envio_usuario_id_usuario')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_envio'))
    )
    op.create_index(op.f('ix_envio_equipamento_id'), 'envio', ['equipamento_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_envio_equipamento_id'), table_name='envio')
    op.drop_table('envio')
    op.drop_table('equipamento')
    op.drop_table('usuario')
    op.drop_table('tipo_sensor')
