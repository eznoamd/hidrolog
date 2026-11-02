"""Dados do termometro de exemplo: tabela, leitura dos arquivos, consultas e exportacao."""

import csv
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column

from hidrolog_nucleo.plugin import (
    Base, FormatoExportacao, PlanoImportacao, Recusa, ResultadoExportacao, Unidade, obter_equipamento_orm,
    sessao_autorizada,
)


class TermometroLeitura(Base):
    __tablename__ = "termometro_leitura"
    __table_args__ = (UniqueConstraint("equipamento_id", "tempo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamento.id"))
    envio_id: Mapped[int] = mapped_column(ForeignKey("envio.id"), index=True)
    tempo: Mapped[datetime] = mapped_column(DateTime)
    temperatura: Mapped[Optional[float]] = mapped_column(Float, comment="graus Celsius")


# ------------------------------------------------------------------ ingestao

def reconhecer(arvore, verificar=False):
    """Cada .csv com a coluna temperatura_c e uma unidade; o resto e ignorado."""
    csvs = [a for a in arvore.com_extensao(".csv") if "temperatura_c" in a.primeira_linha()]
    if not csvs:
        return Recusa("nenhum .csv com a coluna temperatura_c")
    return PlanoImportacao(unidades=[Unidade(a.caminho, [a]) for a in csvs],
                           ignorados=[(a, "nao e um .csv do termometro") for a in arvore if a not in csvs])


def ler(unidade):
    """Uma leitura por linha, em fluxo."""
    for linha in unidade.arquivo.linhas_csv():
        texto = (linha.get("temperatura_c") or "").strip().replace(",", ".")
        yield {"tempo": datetime.fromisoformat(linha["data_hora"].strip()),
               "temperatura": float(texto) if texto else None}


# ------------------------------------------------------------------ consultas (perfil leitura)

def buscar(usuario, equipamento_id, inicio=None, fim=None) -> list[tuple[datetime, Optional[float]]]:
    """[(tempo, temperatura)] em ordem de tempo."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        obter_equipamento_orm(sessao, equipamento_id, "termometro")
        consulta = select(TermometroLeitura.tempo, TermometroLeitura.temperatura).where(
            TermometroLeitura.equipamento_id == equipamento_id)
        if inicio is not None:
            consulta = consulta.where(TermometroLeitura.tempo >= inicio)
        if fim is not None:
            consulta = consulta.where(TermometroLeitura.tempo <= fim)
        return [tuple(l) for l in sessao.execute(consulta.order_by(TermometroLeitura.tempo))]


# ------------------------------------------------------------------ exportacao

FORMATOS = (FormatoExportacao("csv", "CSV (tempo, temperatura, qualidade)", ".csv", "text/csv"),)


def exportar(sessao, equipamento_id, inicio, fim, formato, destino, contexto):
    consulta = select(TermometroLeitura).where(TermometroLeitura.equipamento_id == equipamento_id)
    if inicio is not None:
        consulta = consulta.where(TermometroLeitura.tempo >= inicio)
    if fim is not None:
        consulta = consulta.where(TermometroLeitura.tempo <= fim)
    resultado = ResultadoExportacao()
    with open(destino, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(["tempo", "temperatura_C", "qualidade"])
        for l in sessao.scalars(consulta.order_by(TermometroLeitura.tempo)):
            escritor.writerow([l.tempo.isoformat(), "" if l.temperatura is None else l.temperatura,
                               contexto.qualidade(l.tempo)])
            resultado.leituras += 1
            resultado.inicio = resultado.inicio or l.tempo
            resultado.fim = l.tempo
    return resultado
