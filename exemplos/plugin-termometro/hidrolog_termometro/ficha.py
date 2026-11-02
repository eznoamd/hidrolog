"""Campos que o termometro acrescenta ao cadastro do equipamento."""

from hidrolog_nucleo.plugin import Campo

FICHA = (
    Campo("intervalo_esperado_s", "Intervalo de amostragem esperado", tipo="inteiro", unidade="s",
          padrao=600, minimo=1, maximo=86400, ajuda="Tempo entre duas leituras do termômetro."),
    Campo("altura_m", "Altura do sensor", tipo="decimal", unidade="m", minimo=0, maximo=100),
)
