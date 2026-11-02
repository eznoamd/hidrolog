"""Exportação da estação: CSV e JSON (com os metadados da instalação)."""

from __future__ import annotations

import csv
import json

from sqlalchemy import select

from hidrolog_nucleo.plugin import FormatoExportacao, ResultadoExportacao

from .dados import EstacaoLeitura as L

FORMATOS = (
    FormatoExportacao("csv", "CSV (uma linha por leitura)", ".csv", "text/csv"),
    FormatoExportacao("json", "JSON (leituras + metadados)", ".json", "application/json"),
)
COLUNAS_CSV = ("tempo", "arquivo", "chuva_mm_h", "temperatura_C", "status", "tensao_V", "qualidade")


def _leituras(sessao, equipamento_id, inicio, fim):
    consulta = select(L).where(L.equipamento_id == equipamento_id, L.corrompido.is_(False))
    if inicio is not None:
        consulta = consulta.where(L.tempo >= inicio)
    if fim is not None:
        consulta = consulta.where(L.tempo <= fim)
    return sessao.scalars(consulta.order_by(L.tempo))


def exportar(sessao, equipamento_id, inicio, fim, formato, destino, contexto) -> ResultadoExportacao:
    resultado = ResultadoExportacao()
    linhas = []
    for l in _leituras(sessao, equipamento_id, inicio, fim):
        linhas.append({"tempo": l.tempo.isoformat(), "arquivo": l.arquivo, "chuva_mm_h": l.chuva,
                       "temperatura_C": l.temperatura, "status": l.status, "tensao_V": l.tensao,
                       "qualidade": contexto.qualidade(l.tempo)})
        resultado.leituras += 1
        resultado.inicio = resultado.inicio or l.tempo
        resultado.fim = l.tempo
    if formato == "csv":
        with open(destino, "w", newline="", encoding="utf-8") as f:
            escritor = csv.DictWriter(f, fieldnames=COLUNAS_CSV)
            escritor.writeheader()
            escritor.writerows({k: ("" if v is None else v) for k, v in l.items()} for l in linhas)
    else:
        eq = contexto.equipamento
        with open(destino, "w", encoding="utf-8") as f:
            json.dump({"equipamento": eq.nome, "numero_serie": eq.numero_serie,
                       "institution": contexto.instituicao, "leituras": linhas}, f, ensure_ascii=False)
    return resultado
