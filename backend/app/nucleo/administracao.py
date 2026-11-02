"""Operacoes so do comando de linha (nao fazem parte da camada de servico
que o app chama): criar o master e redefinir senha esquecida. Quem roda o
comando ja tem acesso ao arquivo do banco."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from .banco import Banco
from .erros import Conflito, NaoEncontrado
from .modelos import Usuario
from .seguranca import gerar_hash


def criar_master(banco: Banco, login: str, nome: str, senha: str) -> None:
    """So funciona se ainda nao houver nenhum master (primeira execucao)."""
    login = login.strip()
    with banco.sessao() as sessao:
        if sessao.scalar(select(Usuario.id).where(Usuario.perfil == "master")) is not None:
            raise Conflito("ja existe um master; use redefinir-senha se esqueceu a senha")
        if sessao.scalar(select(Usuario.id).where(Usuario.login == login)) is not None:
            raise Conflito(f"ja existe o usuario '{login}'")
        sessao.add(Usuario(login=login, nome=nome or login, senha_hash=gerar_hash(senha),
                           perfil="master", ativo=True, criado_em=datetime.now()))


def redefinir_senha(banco: Banco, login: str, senha: str) -> None:
    with banco.sessao() as sessao:
        usuario = sessao.scalar(select(Usuario).where(Usuario.login == login.strip()))
        if usuario is None:
            raise NaoEncontrado(f"usuario '{login}' nao encontrado")
        usuario.senha_hash = gerar_hash(senha)
        usuario.ativo = True
