"""Conexao com o banco e migracoes (Alembic).

Um banco so: as tabelas do nucleo e as de cada plugin ficam no mesmo
arquivo SQLite (padrao: <diretorio de dados do usuario>/hidrolog.db) ou no
banco de DATABASE_URL.

Migracoes: o nucleo tem a historia dele (app/nucleo/migracoes/versions,
branch "nucleo") e cada plugin tem a sua, num diretorio proprio
(Plugin.migracoes), como um branch do Alembic com branch_labels=(codigo,)
e depends_on a revisao do nucleo de que precisa. Abrir o banco sobe o
branch do nucleo e o de cada plugin carregado ("<codigo>@head"); um plugin
desativado nao sobe, mas as revisoes dele continuam conhecidas (os dados
ficam). Antes de rodar migracoes de plugin num banco que ja existe, o
arquivo do banco e copiado (backup_banco)."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from . import plugins
from .modelos import TipoSensor

DIRETORIO_MIGRACOES = Path(__file__).parent / "migracoes"
log = logging.getLogger("hidrolog.banco")


def _pragmas_sqlite(conexao_dbapi, _registro):
    cursor = conexao_dbapi.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")      # leitores nao bloqueiam a importacao
    cursor.execute("PRAGMA synchronous=NORMAL")    # seguro com WAL e bem mais rapido
    cursor.close()


def config_alembic(url: str) -> Config:
    """Configuracao do Alembic montada em codigo (nao ha alembic.ini): o
    nucleo + os diretorios de migracao de todos os plugins registrados."""
    cfg = Config()
    cfg.set_main_option("script_location", str(DIRETORIO_MIGRACOES))
    locais = [DIRETORIO_MIGRACOES / "versions"]
    locais += [p.migracoes for p in plugins.todos() if p.migracoes]
    locais += [l for l in plugins.migracoes_inativas() if l not in locais]
    cfg.set_main_option("version_locations", " ".join(str(l) for l in locais))
    cfg.set_main_option("path_separator", "space")
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


class Banco:
    """Engine + fabrica de sessoes. Ao abrir, aplica as migracoes pendentes
    (de todos os plugins registrados) e sincroniza a tabela tipo_sensor."""

    def __init__(self, url: str, migrar: bool = True):
        self.url = url
        argumentos = {}
        if url.startswith("sqlite"):
            # a API roda as operacoes em threads do threadpool
            argumentos["connect_args"] = {"check_same_thread": False}
        self.engine: Engine = create_engine(url, **argumentos)
        if self.engine.dialect.name == "sqlite":
            event.listen(self.engine, "connect", _pragmas_sqlite)
        self._fabrica = sessionmaker(self.engine, expire_on_commit=False)
        self.backups: list[Path] = []
        self.migracoes_aplicadas: list[str] = []
        self.revisoes_ausentes: list[str] = []
        if migrar:
            self.migrar()
        self.sincronizar_tipos()

    def migrar(self) -> list[Path]:
        """Sobe o nucleo e cada plugin carregado. Devolve os backups feitos
        (antes de migracoes de plugin num banco ja existente)."""
        cfg = config_alembic(self.url)
        script = ScriptDirectory.from_config(cfg)
        rotulos = {r for rev in script.walk_revisions() for r in (rev.branch_labels or ())}
        alvos = ["nucleo@head"] + [f"{p.codigo}@head" for p in plugins.todos() if p.codigo in rotulos]
        self.backups: list[Path] = []
        with self.engine.connect() as conexao:
            ja_existe = "alembic_version" in inspect(conexao).get_table_names()
            heads = MigrationContext.configure(conexao).get_current_heads()
        # revisoes de plugins que sumiram (pacote removido): ficam guardadas a parte
        # durante a migracao, para o Alembic nao falhar, e voltam no fim (os dados ficam)
        conhecidas = {r.revision for r in script.walk_revisions()}
        ausentes = [h for h in heads if h not in conhecidas]
        if ausentes:
            log.warning("revisoes de plugins ausentes no banco (dados preservados): %s", ausentes)
        aplicadas = _aplicadas(script, [h for h in heads if h in conhecidas])
        pendentes = sorted({r for p in plugins.todos() if p.codigo in rotulos
                            for r in _revisoes_do_ramo(script, p.codigo) if r not in aplicadas})
        if ja_existe and pendentes:
            destino = backup_banco(self.url, "antes-migrar-" + "-".join(pendentes))
            if destino is not None:
                self.backups.append(destino)
                log.info("backup do banco antes das migracoes de plugin %s: %s", pendentes, destino)
        self.migracoes_aplicadas = pendentes
        with self.engine.begin() as conexao:
            for rev in ausentes:
                conexao.execute(text("DELETE FROM alembic_version WHERE version_num = :v"), {"v": rev})
            cfg.attributes["connection"] = conexao
            for alvo in alvos:
                command.upgrade(cfg, alvo)
            for rev in ausentes:
                conexao.execute(text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": rev})
        self.revisoes_ausentes = ausentes
        return self.backups

    def sincronizar_tipos(self) -> None:
        """Um tipo_sensor por plugin carregado (os de plugins ausentes ficam:
        os equipamentos e os dados deles continuam no banco)."""
        with self.sessao() as sessao:
            existentes = {t.codigo: t for t in sessao.scalars(select(TipoSensor))}
            for plugin in plugins.todos():
                tipo = existentes.get(plugin.codigo)
                if tipo is None:
                    sessao.add(TipoSensor(codigo=plugin.codigo, nome=plugin.nome))
                elif tipo.nome != plugin.nome:
                    tipo.nome = plugin.nome

    @contextmanager
    def sessao(self) -> Iterator[Session]:
        """Uma sessao com uma transacao: commit no fim, rollback se der erro."""
        with self._fabrica() as sessao:
            with sessao.begin():
                yield sessao

    def fechar(self) -> None:
        self.engine.dispose()


def _revisoes_do_ramo(script: ScriptDirectory, rotulo: str) -> set[str]:
    """As revisoes do branch (seguindo down_revision a partir do head)."""
    saida: set[str] = set()
    pilha = [r.revision for r in script.get_revisions(f"{rotulo}@head")]
    while pilha:
        rev = script.get_revision(pilha.pop())
        if rev is None or rev.revision in saida:
            continue
        saida.add(rev.revision)
        pilha.extend(rev._versioned_down_revisions)
    return saida


def _aplicadas(script: ScriptDirectory, heads) -> set[str]:
    """Todas as revisoes ja aplicadas (os heads e tudo abaixo deles)."""
    saida: set[str] = set()
    conhecidas = {r.revision for r in script.walk_revisions()}
    pilha = [h for h in (heads or ()) if h in conhecidas]
    while pilha:
        rev = script.get_revision(pilha.pop())
        if rev is None or rev.revision in saida:
            continue
        saida.add(rev.revision)
        pilha.extend(rev._all_down_revisions)
    return saida


def caminho_sqlite(url: str) -> Optional[Path]:
    """O arquivo de um banco SQLite (None se nao for SQLite em arquivo)."""
    if not url.startswith("sqlite:///"):
        return None
    caminho = url[len("sqlite:///"):]
    return Path(caminho) if caminho and caminho != ":memory:" else None


def backup_banco(url: str, motivo: str = "backup") -> Optional[Path]:
    """Copia o banco SQLite (API de backup do SQLite: consistente mesmo com o
    WAL) para <banco>.backup-<data>-<motivo>.db, na mesma pasta."""
    origem = caminho_sqlite(url)
    if origem is None or not origem.exists():
        return None
    motivo = "".join(c if c.isalnum() or c in "-_" else "-" for c in motivo)[:80]
    destino = origem.with_name(f"{origem.stem}.backup-{datetime.now():%Y%m%d-%H%M%S}-{motivo}.db")
    fonte, copia = sqlite3.connect(str(origem)), sqlite3.connect(str(destino))
    try:
        fonte.backup(copia)
    finally:
        copia.close()
        fonte.close()
    return destino
