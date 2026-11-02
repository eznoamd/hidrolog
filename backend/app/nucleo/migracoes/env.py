"""Ambiente do Alembic. Usado por app.nucleo.banco (que passa a conexao em
config.attributes["connection"]) e pelo comando `python -m app nova-migracao`."""

from alembic import context
from sqlalchemy import create_engine

from app.nucleo import plugins
from app.nucleo.modelos import Base

plugins.carregar()
for _plugin in plugins.todos():
    _plugin.modelos  # importar o plugin ja registrou as tabelas dele na Base

config = context.config


def _rodar(conexao):
    context.configure(
        connection = conexao,
        target_metadata = Base.metadata,
        render_as_batch = True,        # ALTER TABLE no SQLite
        compare_type = True,
    )
    with context.begin_transaction():
        context.run_migrations()


conexao = config.attributes.get("connection")
if conexao is not None:
    _rodar(conexao)
else:
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    with engine.begin() as nova:
        _rodar(nova)
