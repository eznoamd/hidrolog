"""Regras de qualidade da estação: declarativas e por função, nos três níveis."""

from datetime import timedelta

from sqlalchemy import func, select

from hidrolog_nucleo.plugin import Ocorrencia, Regra

from .dados import EstacaoLeitura as L


def _leituras_faltando(ctx):
    """Nível envio: lacunas maiores que fator x intervalo no período do envio."""
    if ctx.inicio is None or ctx.fim is None:
        return []
    intervalo = float(ctx.equipamento.atributos.get("intervalo_s") or ctx.parametros["intervalo_padrao_s"])
    tempos = list(ctx.sessao.scalars(select(L.tempo).where(
        L.equipamento_id == ctx.equipamento.id, L.tempo >= ctx.inicio, L.tempo <= ctx.fim).order_by(L.tempo)))
    limite = intervalo * ctx.parametros["fator_lacuna"]
    lacunas = [(a, b) for a, b in zip(tempos, tempos[1:]) if (b - a).total_seconds() > limite]
    if not lacunas:
        return []
    faltando = sum(round((b - a).total_seconds() / intervalo) - 1 for a, b in lacunas)
    if faltando < ctx.parametros["minimo_faltando"]:
        return []
    return [Ocorrencia(f"{faltando} leitura(s) faltando (intervalo de {intervalo:.0f} s)", lacunas[0][0])]


def _sem_dados(ctx):
    ultima = ctx.sessao.scalar(select(func.max(L.tempo)).where(L.equipamento_id == ctx.equipamento.id))
    dias = ctx.parametros["dias"]
    if ultima is not None and ctx.agora - ultima > timedelta(days=dias):
        return [Ocorrencia(f"sem dados há mais de {dias} dias (última leitura em {ultima:%d/%m/%Y %H:%M})", ultima)]
    return []


def _tensao_baixa(ctx):
    minima = ctx.sessao.scalar(select(func.min(L.tensao)).where(L.equipamento_id == ctx.equipamento.id,
                                                                  L.tensao.isnot(None)))
    if minima is not None and minima < ctx.parametros["minima_v"]:
        return [Ocorrencia(f"tensão mínima de {minima:.1f} V (abaixo de {ctx.parametros['minima_v']} V)")]
    return []


REGRAS = (
    Regra("status_sensor", "Status do sensor diferente de 0", nivel="leitura", severidade="suspeita",
          coluna="status", operador="!=", limite=0, mensagem="status {valor}"),
    Regra("chuva_impossivel", "Chuva acima do limite físico", nivel="leitura", severidade="suspeita",
          parametros={"limite_mm_h": 300.0}, coluna="chuva", operador=">", limite="limite_mm_h",
          mensagem="chuva de {valor:.1f} mm/h acima de {limite_mm_h} mm/h",
          ajuda_parametros={"limite_mm_h": "chuva máxima aceitável (mm/h)"}),
    Regra("leituras_faltando", "Leituras faltando no período do envio", nivel="envio", severidade="aviso",
          parametros={"intervalo_padrao_s": 120, "fator_lacuna": 1.5, "minimo_faltando": 1},
          funcao=_leituras_faltando),
    Regra("sem_dados", "Sem dados há muitos dias", nivel="equipamento", severidade="alerta",
          parametros={"dias": 7}, funcao=_sem_dados, ajuda_parametros={"dias": "dias sem leitura (dias)"}),
    Regra("tensao_baixa", "Tensão de alimentação baixa", nivel="equipamento", severidade="alerta",
          parametros={"minima_v": 11.0}, funcao=_tensao_baixa),
)
