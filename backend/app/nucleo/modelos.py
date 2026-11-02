"""Tabelas do nucleo: usuario, tipo_sensor, equipamento, envio, plugin_instalado
auditoria_plugin, regra_config e ocorrencia.

So tipos genericos do SQLAlchemy: o mesmo modelo serve para SQLite
(padrao) e PostgreSQL. Os plugins declaram as tabelas deles sobre a mesma
Base, no mesmo banco."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, MetaData, Text, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# nomes previsiveis para as constraints (o Alembic precisa deles no SQLite)
_CONVENCAO = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_CONVENCAO)


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login: Mapped[str] = mapped_column(Text, unique=True)
    nome: Mapped[str] = mapped_column(Text)
    senha_hash: Mapped[str] = mapped_column(Text, comment="argon2id (argon2-cffi)")
    perfil: Mapped[str] = mapped_column(Text, comment="master, cadastro ou leitura")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime)


class TipoSensor(Base):
    """Um tipo de sensor (um plugin carregado). Sincronizada com o
    registro de plugins sempre que o banco e aberto."""

    __tablename__ = "tipo_sensor"

    codigo: Mapped[str] = mapped_column(Text, primary_key=True)
    nome: Mapped[str] = mapped_column(Text)


class Equipamento(Base):
    """Uma unidade fisica de um tipo de sensor."""

    __tablename__ = "equipamento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo_sensor: Mapped[str] = mapped_column(ForeignKey("tipo_sensor.codigo"))
    nome: Mapped[str] = mapped_column(Text, unique=True)
    numero_serie: Mapped[Optional[str]] = mapped_column(Text)
    local: Mapped[Optional[str]] = mapped_column(Text)
    observacoes: Mapped[Optional[str]] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime)
    latitude: Mapped[Optional[float]] = mapped_column(Float, comment="graus decimais, WGS84")
    longitude: Mapped[Optional[float]] = mapped_column(Float, comment="graus decimais, WGS84")
    altitude_m: Mapped[Optional[float]] = mapped_column(Float, comment="metros acima do nivel do mar")
    instalado_em: Mapped[Optional[date]] = mapped_column(Date)
    atributos: Mapped[Optional[dict]] = mapped_column(JSON, comment="ficha do plugin (validada por ele): {campo: valor}")
    versao_ficha: Mapped[Optional[int]] = mapped_column(
        Integer, comment="versao da ficha do plugin quando os atributos foram gravados")


class Envio(Base):
    """Uma importacao (caminho local ou upload) para um equipamento, com o
    resumo dela. As contagens de leituras vem do plugin do sensor."""

    __tablename__ = "envio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamento.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    recebido_em: Mapped[datetime] = mapped_column(DateTime)
    canal: Mapped[str] = mapped_column(Text, comment="local ou upload")
    tipo: Mapped[str] = mapped_column(Text, comment="zip, rar, pasta, arquivos ou misto")
    origem: Mapped[str] = mapped_column(Text, comment="nome(s) do arquivo ou caminho")

    arquivos_recebidos: Mapped[int] = mapped_column(Integer, default=0, comment="todos, inclusive ignorados")
    ignorados: Mapped[int] = mapped_column(Integer, default=0, comment="arquivos que nao sao do sensor")
    leituras: Mapped[int] = mapped_column(Integer, default=0, comment="arquivos de dados do sensor")
    validas: Mapped[int] = mapped_column(Integer, default=0)
    corrompidas: Mapped[int] = mapped_column(Integer, default=0)
    novas: Mapped[int] = mapped_column(Integer, default=0, comment="inseridas (validas e corrompidas)")
    duplicadas: Mapped[int] = mapped_column(Integer, default=0, comment="ja no banco ou repetidas no envio")
    inicio: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="primeira leitura do envio")
    fim: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="ultima leitura do envio")
    duracao_s: Mapped[float] = mapped_column(Float, default=0.0, comment="tempo da importacao")
    avisos: Mapped[Optional[str]] = mapped_column(Text)

    equipamento: Mapped[Equipamento] = relationship(lazy="joined")
    usuario: Mapped[Usuario] = relationship(lazy="joined")


class PluginInstalado(Base):
    """Uma versao de plugin que o app conhece: instalada pelo gerenciador
    (pasta, zip, GitHub) ou interna (entry point). situacao: ativo, guardada
    (versao anterior, para voltar), desativado, incompativel ou com falha."""

    __tablename__ = "plugin_instalado"
    __table_args__ = (UniqueConstraint("codigo", "versao"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text, index=True)
    nome: Mapped[str] = mapped_column(Text)
    versao: Mapped[str] = mapped_column(Text)
    contrato: Mapped[str] = mapped_column(Text, comment="versao do contrato declarada, ex. 1.x")
    origem: Mapped[str] = mapped_column(Text, comment="interno, pasta, zip ou github")
    url: Mapped[Optional[str]] = mapped_column(Text, comment="github: URL do repositorio")
    tag: Mapped[Optional[str]] = mapped_column(Text, comment="github: tag ou release")
    sha256: Mapped[Optional[str]] = mapped_column(Text, comment="hash do pacote importado")
    caminho: Mapped[Optional[str]] = mapped_column(Text)
    instalado_por: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"))
    instalado_em: Mapped[datetime] = mapped_column(DateTime)
    situacao: Mapped[str] = mapped_column(Text)
    motivo: Mapped[Optional[str]] = mapped_column(Text)


class AuditoriaPlugin(Base):
    """Cada acao do gerenciador de plugins (e cada senha errada), com o resultado."""

    __tablename__ = "auditoria_plugin"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quando: Mapped[datetime] = mapped_column(DateTime, index=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"))
    login: Mapped[str] = mapped_column(Text, comment="quem (copia do login, fica mesmo se o usuario mudar)")
    acao: Mapped[str] = mapped_column(Text, comment="importar, atualizar, desativar, reativar, voltar_versao, "
                                                    "remover, migrar, senha")
    codigo: Mapped[Optional[str]] = mapped_column(Text)
    versao: Mapped[Optional[str]] = mapped_column(Text)
    origem: Mapped[Optional[str]] = mapped_column(Text)
    resultado: Mapped[str] = mapped_column(Text, comment="ok, recusado, cancelado ou erro")
    detalhes: Mapped[Optional[str]] = mapped_column(Text)


class RegraConfig(Base):
    """Parametros de uma regra de qualidade ajustados para um equipamento
    (perfil cadastro ou superior), com quem alterou e quando."""

    __tablename__ = "regra_config"
    __table_args__ = (UniqueConstraint("equipamento_id", "codigo_regra"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamento.id"))
    codigo_regra: Mapped[str] = mapped_column(Text)
    parametros: Mapped[Optional[dict]] = mapped_column(JSON, comment="so os que mudam do padrao da regra")
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    alterada_por: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"))
    alterada_em: Mapped[datetime] = mapped_column(DateTime)


class Ocorrencia(Base):
    """O que uma regra de qualidade encontrou. Regras nunca alteram dados:
    so criam (e resolvem) ocorrencias ligadas a leitura (tempo), ao envio ou
    ao equipamento."""

    __tablename__ = "ocorrencia"
    __table_args__ = (Index("ix_ocorrencia_equipamento_tempo", "equipamento_id", "tempo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamento.id"))
    envio_id: Mapped[Optional[int]] = mapped_column(ForeignKey("envio.id"))
    tempo: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="leitura (nivel leitura) ou instante do problema")
    codigo_regra: Mapped[str] = mapped_column(Text)
    nivel: Mapped[str] = mapped_column(Text, comment="leitura, envio ou equipamento")
    severidade: Mapped[str] = mapped_column(Text, comment="aviso, suspeita ou alerta")
    mensagem: Mapped[str] = mapped_column(Text)
    criada_em: Mapped[datetime] = mapped_column(DateTime)
    resolvida_por: Mapped[Optional[int]] = mapped_column(ForeignKey("usuario.id"))
    resolvida_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime, comment="resolvida (resolvida_por nulo = a condicao deixou de valer)")
