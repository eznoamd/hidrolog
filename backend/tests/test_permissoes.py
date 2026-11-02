"""Usuarios e perfis, na camada de servico (sem HTTP)."""

import dataclasses

import pytest

from app import servico
from app.nucleo.administracao import criar_master, redefinir_senha
from app.nucleo.erros import Conflito, ErroAutenticacao, ErroPermissao, ErroServico

from .conftest import PASTA_DADOS, SENHA


def test_autenticar(master):
    assert master.perfil == "master" and master.login == "admin"
    with pytest.raises(ErroAutenticacao):
        servico.autenticar("admin", "senha errada")
    with pytest.raises(ErroAutenticacao):
        servico.autenticar("ninguem", SENHA)


def test_senha_guardada_com_argon2(master, banco):
    from app.nucleo.modelos import Usuario
    with banco.sessao() as sessao:
        hash_ = sessao.get(Usuario, master.id).senha_hash
    assert hash_.startswith("$argon2id$") and SENHA not in hash_


def test_master_so_pelo_comando_de_linha(master, banco):
    assert not hasattr(servico, "criar_master")
    with pytest.raises(ErroPermissao):
        servico.criar_usuario(master, "outro", "Outro", SENHA, "master")
    with pytest.raises(Conflito):
        criar_master(banco, "admin2", "Outro master", SENHA)   # so na primeira execucao


def test_master_nao_e_promovido_nem_rebaixado_pelo_app(master, cadastro):
    with pytest.raises(ErroPermissao):
        servico.alterar_usuario(master, cadastro.id, perfil="master")
    with pytest.raises(ErroPermissao):
        servico.alterar_usuario(master, master.id, perfil="leitura")
    with pytest.raises(ErroPermissao):
        servico.alterar_usuario(master, master.id, ativo=False)


def test_master_gerencia_usuarios(master, cadastro, leitor):
    assert [u.login for u in servico.listar_usuarios(master)] == ["admin", "cad", "ler"]
    alterado = servico.alterar_usuario(master, leitor.id, nome="Novo nome", perfil="cadastro")
    assert (alterado.nome, alterado.perfil) == ("Novo nome", "cadastro")
    servico.trocar_senha(master, leitor.id, "outra-senha-123")
    assert servico.autenticar("ler", "outra-senha-123").perfil == "cadastro"
    with pytest.raises(Conflito):
        servico.criar_usuario(master, "ler", "Repetido", SENHA)
    with pytest.raises(ErroServico):
        servico.criar_usuario(master, "curta", "Senha curta", "123")


def test_cadastro_nao_gerencia_usuarios(cadastro, leitor):
    with pytest.raises(ErroPermissao):
        servico.criar_usuario(cadastro, "x", "X", SENHA, "leitura")
    with pytest.raises(ErroPermissao):
        servico.listar_usuarios(cadastro)
    with pytest.raises(ErroPermissao):
        servico.trocar_senha(cadastro, leitor.id, "qualquer-coisa")
    with pytest.raises(ErroPermissao):
        servico.alterar_usuario(cadastro, leitor.id, ativo=False)


def test_leitura_nao_importa_nem_cadastra(leitor, equipamento):
    with pytest.raises(ErroPermissao):
        servico.importar_caminho(leitor, equipamento.id, PASTA_DADOS)
    with pytest.raises(ErroPermissao):
        servico.criar_equipamento(leitor, "estacao", "Outro")
    # mas consulta
    assert [e.nome for e in servico.listar_equipamentos(leitor)] == ["Estação teste"]
    assert servico.listar_envios(leitor) == []


def test_cadastro_importa_e_consulta(cadastro, equipamento):
    resumo = servico.importar_caminho(cadastro, equipamento.id, PASTA_DADOS)
    assert resumo.usuario == "cad"
    assert servico.listar_envios(cadastro)[0].id == resumo.id
    assert servico.obter_envio(cadastro, resumo.id).novas == 13


def test_usuario_desativado_perde_acesso_na_hora(master, leitor):
    servico.alterar_usuario(master, leitor.id, ativo=False)
    with pytest.raises(ErroAutenticacao):
        servico.listar_equipamentos(leitor)       # o objeto antigo nao vale mais
    with pytest.raises(ErroAutenticacao):
        servico.autenticar("ler", SENHA)


def test_perfil_e_conferido_no_banco_e_nao_no_objeto(leitor, equipamento):
    falso_master = dataclasses.replace(leitor, perfil="master")
    with pytest.raises(ErroPermissao):
        servico.listar_usuarios(falso_master)
    with pytest.raises(ErroPermissao):
        servico.importar_caminho(falso_master, equipamento.id, PASTA_DADOS)


def test_redefinir_senha_pelo_comando_de_linha(master, banco):
    redefinir_senha(banco, "admin", "nova-senha-123")
    assert servico.autenticar("admin", "nova-senha-123").perfil == "master"


def test_equipamentos(cadastro, leitor):
    assert {t.codigo for t in servico.listar_tipos_sensor()} >= {"estacao", "falso"}
    eq = servico.criar_equipamento(cadastro, "estacao", "P1", numero_serie="1", local="Campus")
    with pytest.raises(Conflito):
        servico.criar_equipamento(cadastro, "estacao", "P1")
    with pytest.raises(ErroServico):
        servico.criar_equipamento(cadastro, "nao_existe", "P2")
    servico.alterar_equipamento(cadastro, eq.id, local="Telhado", ativo=False)
    assert servico.listar_equipamentos(leitor) == []
    assert servico.listar_equipamentos(leitor, incluir_inativos=True)[0].local == "Telhado"
    with pytest.raises(ErroServico, match="desativado"):
        servico.importar_caminho(cadastro, eq.id, PASTA_DADOS)


def test_a_propria_conta(leitor, master, equipamento):
    alterado = servico.alterar_meu_nome(leitor, "  Leitora Nova  ")
    assert alterado.nome == "Leitora Nova" and alterado.login == leitor.login
    with pytest.raises(ErroServico):
        servico.alterar_meu_nome(leitor, "   ")
    with pytest.raises(ErroServico):                       # senha atual errada: a sessao continua
        servico.trocar_minha_senha(leitor, "errada-123", "nova-senha-123")
    with pytest.raises(ErroServico):
        servico.trocar_minha_senha(leitor, SENHA, SENHA)
    with pytest.raises(ErroServico):
        servico.trocar_minha_senha(leitor, SENHA, "curta")
    servico.trocar_minha_senha(leitor, SENHA, "nova-senha-123")
    assert servico.autenticar(leitor.login, "nova-senha-123").id == leitor.id
    with pytest.raises(ErroAutenticacao):
        servico.autenticar(leitor.login, SENHA)
    assert servico.meus_envios(leitor) == []
    resumo = servico.importar_caminho(master, equipamento.id, PASTA_DADOS)
    assert [e.id for e in servico.meus_envios(master)] == [resumo.id]
    assert servico.meus_envios(leitor) == []
