"""Regras de qualidade do termometro: uma declarativa e uma por funcao."""

from datetime import timedelta

from sqlalchemy import func, select

from hidrolog_nucleo.plugin import Ocorrencia, Regra


def _sem_dados(ctx):
    """Nivel equipamento: a ultima leitura e mais antiga que N dias."""
    from .dados import TermometroLeitura

    ultima = ctx.sessao.scalar(select(func.max(TermometroLeitura.tempo))
                               .where(TermometroLeitura.equipamento_id == ctx.equipamento.id))
    dias = ctx.parametros["dias"]
    if ultima is not None and ctx.agora - ultima > timedelta(days=dias):
        return [Ocorrencia(f"sem dados desde {ultima:%d/%m/%Y %H:%M} (mais de {dias} dias)", ultima)]
    return []


REGRAS = (
    Regra("temperatura_impossivel", "Temperatura fora da faixa física do sensor", nivel="leitura",
          severidade="suspeita", parametros={"maxima_c": 60.0}, coluna="temperatura", operador=">",
          limite="maxima_c", mensagem="temperatura de {valor:.1f} °C acima de {maxima_c} °C",
          ajuda_parametros={"maxima_c": "temperatura máxima aceitável (°C)"}),
    Regra("sem_dados", "Sem dados há muitos dias", nivel="equipamento", severidade="alerta",
          parametros={"dias": 7}, funcao=_sem_dados, ajuda_parametros={"dias": "dias sem leitura (dias)"}),
)
