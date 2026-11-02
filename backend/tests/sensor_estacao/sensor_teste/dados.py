"""Tabela e ingestão da estação de teste."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import PurePosixPath
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from hidrolog_nucleo.plugin import Base, PlanoImportacao, Recusa, Unidade

NOME_LEITURA = re.compile(r"^(\d{14})\.txt$")
NUMERICOS = {"chuva": float, "temperatura": float, "status": int, "tensao": float, "intervalo": int}
TEXTOS = {"serie": "numero_serie", "firmware": "firmware"}


class EstacaoLeitura(Base):
    __tablename__ = "estacao_leitura"
    __table_args__ = (UniqueConstraint("equipamento_id", "tempo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamento.id"))
    envio_id: Mapped[int] = mapped_column(ForeignKey("envio.id"), index=True)
    tempo: Mapped[datetime] = mapped_column(DateTime)
    arquivo: Mapped[str] = mapped_column(String(64))
    corrompido: Mapped[bool] = mapped_column(Boolean, default=False)
    chuva: Mapped[Optional[float]] = mapped_column(Float, comment="mm/h")
    temperatura: Mapped[Optional[float]] = mapped_column(Float, comment="graus Celsius")
    status: Mapped[Optional[int]] = mapped_column(Integer)
    tensao: Mapped[Optional[float]] = mapped_column(Float, comment="V")
    intervalo: Mapped[Optional[int]] = mapped_column(Integer, comment="s")
    numero_serie: Mapped[Optional[str]] = mapped_column(String(32))
    firmware: Mapped[Optional[str]] = mapped_column(String(32))


def tempo_do_nome(nome: str) -> Optional[datetime]:
    m = NOME_LEITURA.match(PurePosixPath(nome).name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def reconhecer(arvore, verificar=False):
    """Cada AAAAMMDDHHMMSS.txt (com data válida) é uma leitura; o resto é ignorado."""
    leituras = [a for a in arvore if tempo_do_nome(a.nome) is not None]
    if not leituras:
        return Recusa("nenhuma leitura AAAAMMDDHHMMSS.txt da estação")
    return PlanoImportacao(unidades=[Unidade(a.caminho, [a]) for a in leituras],
                           ignorados=[(a, "não é uma leitura da estação") for a in arvore if a not in leituras])


def interpretar(texto: str) -> dict:
    """Campos de um arquivo; `corrompido` se faltar a chuva ou um valor não for número."""
    linha = {"corrompido": False}
    for bruta in texto.splitlines():
        chave, _, valor = bruta.strip().partition(":")
        valor = valor.strip()
        if chave in NUMERICOS:
            try:
                linha[chave] = NUMERICOS[chave](valor)
            except ValueError:
                linha["corrompido"] = True
        elif chave in TEXTOS and valor:
            linha[TEXTOS[chave]] = valor
    if "chuva" not in linha:
        linha["corrompido"] = True
    return linha


def ler(unidade):
    arquivo = unidade.arquivo
    linha = interpretar(arquivo.texto())
    linha["tempo"] = tempo_do_nome(arquivo.nome)
    linha["arquivo"] = PurePosixPath(arquivo.nome).name
    yield linha
