"""Campos que a estação acrescenta ao cadastro: um digitado e dois lidos dos dados."""

from hidrolog_nucleo.plugin import Campo

VERSAO_FICHA = 2

FICHA = (
    Campo("intervalo_s", "Intervalo de amostragem", tipo="inteiro", unidade="s", padrao=120, minimo=1,
          maximo=3600, ajuda="Tempo entre duas leituras (usado quando os dados não trazem o intervalo)."),
    Campo("firmware", "Versão do firmware", tipo="texto", somente_leitura=True, origem="leituras",
          coluna="firmware"),
    Campo("numero_serie_lido", "Nº de série nas leituras", tipo="texto", somente_leitura=True,
          origem="leituras", coluna="numero_serie"),
)


def migrar_atributos(atributos: dict, versao_antiga: int) -> dict:
    """Versão 1 tinha a altura do sensor (removida na 2)."""
    if versao_antiga < 2:
        atributos.pop("altura_m", None)
    return atributos
