"""O catálogo de componentes do design abre todas as seções nos dois temas,
sem dados reais nem rede (o mapa fica no modo sem conexão nos testes)."""

import importlib.util

import pytest

from design.tema import aplicar_tema

from .conftest import RAIZ


@pytest.fixture
def catalogo_mod():
    caminho = RAIZ / "design" / "catalogo.py"
    spec = importlib.util.spec_from_file_location("catalogo_design", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize("modo", ["claro", "escuro"])
def test_todas_as_secoes_abrem(qapp, qtbot, catalogo_mod, modo):
    aplicar_tema(qapp, modo)
    try:
        cat = catalogo_mod.Catalogo()
        qtbot.addWidget(cat)
        cat.resize(*catalogo_mod.TAMANHO)
        cat.show()
        for i, (chave, _, _) in enumerate(catalogo_mod.SECOES):
            cat.lista.setCurrentRow(i)
            assert cat.pilha.currentIndex() == i and chave in cat._criadas
            assert not cat.pilha.currentWidget().grab().isNull()
        janela = catalogo_mod.janela_exemplo()
        qtbot.addWidget(janela)
        assert janela.windowTitle() == "Hidrolog"
    finally:
        aplicar_tema(qapp, "claro")
