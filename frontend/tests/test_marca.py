"""Marca da instalação: sem pasta de marca o app é genérico ("Hidrolog" e o
texto "LOGO" no lugar das logos); com a pasta, nomes, logos e mapa vêm dela."""

import pytest
from PySide6.QtGui import QColor, QImage

from design.componentes.logo import LogoInstituicao, LogoMarca
from design.tema import carregar_marca_da_instalacao, definir_marca, marca_atual
from design.tema.marca import POSICAO_PADRAO_MAPA, Marca


@pytest.fixture
def marca_padrao():
    yield
    definir_marca(Marca())          # os outros testes contam com a marca genérica


def _png(caminho):
    imagem = QImage(40, 20, QImage.Format.Format_ARGB32)
    imagem.fill(QColor("#336699"))
    imagem.save(str(caminho))


def test_sem_pasta_de_marca_e_generico(qapp, tmp_path, marca_padrao):
    m = carregar_marca_da_instalacao(tmp_path / "nao-existe")
    assert (m.titulo_janela, m.assinatura, m.laboratorio, m.instituicao) == ("Hidrolog", "", None, None)
    assert m.posicao_padrao_mapa == POSICAO_PADRAO_MAPA
    logo, inst = LogoMarca(altura=60), LogoInstituicao(altura=40)
    assert not logo.tem_imagem
    assert logo._conteudo.text() == "LOGO"
    assert inst.layout().itemAt(0).widget().text() == "LOGO"


def test_pasta_de_marca_da_instalacao(qapp, tmp_path, marca_padrao):
    (tmp_path / "marca.toml").write_text(
        'nome_app = "Hidrolog"\n'
        '[laboratorio]\nsigla = "LAB"\nnome = "Laboratório X"\n'
        '[instituicao]\nsigla = "UNIV"\nnome = "Universidade Y"\n'
        '[mapa]\nposicao_inicial = [-29.7, -53.7]\n', encoding="utf-8")
    _png(tmp_path / "logo.png")
    _png(tmp_path / "instituicao.png")
    m = carregar_marca_da_instalacao(tmp_path)
    assert marca_atual() is m
    assert (m.titulo_janela, m.assinatura) == ("Hidrolog — LAB", "LAB · UNIV")
    assert m.logo == tmp_path / "logo.png" and m.logo_instituicao == tmp_path / "instituicao.png"
    assert m.logo_escura is None and m.posicao_padrao_mapa == (-29.7, -53.7)
    assert LogoMarca(altura=60).tem_imagem


def test_marca_do_instalador_com_campos_vazios_e_bom(tmp_path):
    """O instalador do Windows grava o marca.toml em UTF-8 com BOM e com os campos
    deixados em branco como texto vazio: valem como ausentes."""
    from design.tema.marca import Marca

    (tmp_path / "marca.toml").write_text(
        '\ufeff[laboratorio]\nsigla = "LAB"\nnome = ""\n[instituicao]\nsigla = " "\nnome = ""\n', encoding="utf-8")
    m = Marca.da_pasta(tmp_path)
    assert m.laboratorio == "LAB"
    assert m.laboratorio_completo is None and m.instituicao is None and m.instituicao_sigla is None
