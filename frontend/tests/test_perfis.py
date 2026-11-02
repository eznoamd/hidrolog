"""O que cada perfil vê e o que fica escondido; ErroPermissao com mensagem amigável."""

import pytest

from app.nucleo.erros import ErroPermissao
from hidrolog.nucleo import erros

from .conftest import entrar

GERAIS = ["inicio", "equipamentos", "historico", "exportacao"]


def visiveis(shell) -> set[str]:
    return {c for c, p in shell._paginas.items() if not p.botao.isHidden()}


@pytest.mark.parametrize("perfil,login,veem,nao_veem", [
    ("master", "admin", GERAIS + ["importacao", "usuarios", "configuracoes"], []),
    ("cadastro", "cad", GERAIS + ["importacao"], ["usuarios", "configuracoes"]),
    ("leitura", "ler", GERAIS, ["importacao", "usuarios", "configuracoes"]),
])
def test_navegacao_por_perfil(usuarios, janela, qtbot, perfil, login, veem, nao_veem):
    shell = entrar(janela, qtbot, login)
    assert shell.perfil == perfil
    vistas = visiveis(shell)
    for chave in veem:
        assert chave in vistas, chave
    for chave in nao_veem:
        assert chave not in vistas, chave
        assert shell.ir_para(chave) is None          # nem navegando direto
    assert shell.lateral.isVisible()


def test_leitura_nao_ve_botoes_de_cadastro(usuarios, janela, qtbot):
    shell = entrar(janela, qtbot, "ler")
    eq = shell.ir_para("equipamentos")
    assert eq.novo.isHidden() and eq.editar.isHidden()
    inicio = shell.ir_para("inicio")
    assert "importacao" not in inicio.atalhos
    pag = shell.ir_para("equipamentos")
    assert pag.tabela.linhas() == [] and pag.novo.isHidden()   # sem "Novo equipamento"


def test_cadastro_ve_botoes_de_cadastro(usuarios, janela, qtbot):
    shell = entrar(janela, qtbot, "cad")
    eq = shell.ir_para("equipamentos")
    assert not eq.novo.isHidden() and not eq.editar.isHidden()
    assert "importacao" in shell.ir_para("inicio").atalhos


def test_erro_de_permissao_tem_mensagem_amigavel(usuarios, janela, qtbot):
    shell = entrar(janela, qtbot, "ler")
    pagina = shell.ir_para("equipamentos")
    texto = pagina.mostrar_erro(ErroPermissao("o perfil 'leitura' nao permite esta operacao (precisa de 'cadastro')"))
    assert texto.startswith("Seu perfil (Leitura) não permite esta ação.")
    assert pagina.aviso.isVisible() and "Traceback" not in pagina.aviso.texto.text()
    assert "master não pode ser desativado" in erros.mensagem(
        ErroPermissao("um master nao pode ser desativado pelo app"))
