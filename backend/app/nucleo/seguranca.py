"""Senhas (argon2id) e verificacao de perfil."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .erros import ErroPermissao, ErroServico
from .tipos import PERFIS, Usuario

_hasher = PasswordHasher()
SENHA_MINIMA = 8


def validar_senha(senha: str) -> None:
    if not isinstance(senha, str) or len(senha) < SENHA_MINIMA:
        raise ErroServico(f"a senha precisa de pelo menos {SENHA_MINIMA} caracteres")


def gerar_hash(senha: str) -> str:
    validar_senha(senha)
    return _hasher.hash(senha)


def conferir_senha(senha_hash: str, senha: str) -> bool:
    try:
        return _hasher.verify(senha_hash, senha)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def validar_perfil(perfil: str) -> None:
    if perfil not in PERFIS:
        raise ErroServico(f"perfil invalido: {perfil!r} (use {', '.join(PERFIS)})")


def exigir(usuario: Usuario, perfil: str) -> None:
    if not usuario.pode(perfil):
        raise ErroPermissao(f"o perfil '{usuario.perfil}' nao permite esta operacao (precisa de '{perfil}')")
