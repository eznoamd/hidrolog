"""
Tema Qt do Hidrolog. Identidade (nomes, logos, cores) em marca.py.

Uso no front:

    from design.tema import aplicar_tema
    app = QApplication(sys.argv)
    aplicar_tema(app, "claro")          # ou "escuro"

Tudo o que é visual sai de tokens.py. Os componentes consultam o tema atual
com `cor("primaria")`, `modo_atual()` e recebem a troca de tema pelo sinal
`gerenciador().tema_alterado`.
"""

from __future__ import annotations

from .tokens import CORES, DIMENSAO, ESPACO, FONTE, FORMATO, GRAFICO, MARCA, PERFIS, RAIO, TONS
from .marca import Marca, carregar_marca_da_instalacao, definir_marca, derivar_cores_marca, marca_atual
from .aplicacao import (
    alternar_tema,
    aplicar_tema,
    icone_aplicativo,
    carregar_fontes,
    cor,
    fonte,
    fonte_mono,
    gerenciador,
    icone,
    modo_atual,
    pixmap_icone,
    repolir,
)

__all__ = [
    "CORES", "DIMENSAO", "ESPACO", "FONTE", "FORMATO", "GRAFICO", "MARCA", "PERFIS", "RAIO", "TONS",
    "Marca", "carregar_marca_da_instalacao", "definir_marca", "derivar_cores_marca", "marca_atual", "icone_aplicativo",
    "alternar_tema", "aplicar_tema", "carregar_fontes", "cor", "fonte", "fonte_mono", "gerenciador",
    "icone", "modo_atual", "pixmap_icone", "repolir",
]
