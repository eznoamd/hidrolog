"""Login por token para a API local. Os tokens ficam so na memoria do
processo (somem ao reiniciar) e valem TOKEN_VALIDADE."""

from __future__ import annotations

import secrets
import threading
from datetime import datetime, timedelta

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..nucleo.erros import ErroAutenticacao
from ..nucleo.tipos import Usuario

TOKEN_VALIDADE = timedelta(hours=12)

_tokens: dict[str, tuple[Usuario, datetime]] = {}
_trava = threading.Lock()
_bearer = HTTPBearer(auto_error=False)


def emitir_token(usuario: Usuario) -> str:
    token = secrets.token_urlsafe(32)
    with _trava:
        _tokens[token] = (usuario, datetime.now() + TOKEN_VALIDADE)
    return token


def revogar_token(token: str) -> None:
    with _trava:
        _tokens.pop(token, None)


def usuario_atual(credenciais: HTTPAuthorizationCredentials = Depends(_bearer)) -> Usuario:
    """O servico ainda confere no banco se o usuario esta ativo e o perfil."""
    if credenciais is None:
        raise ErroAutenticacao("faltou o cabecalho Authorization: Bearer <token> (POST /login)")
    with _trava:
        par = _tokens.get(credenciais.credentials)
        if par is None or par[1] < datetime.now():
            _tokens.pop(credenciais.credentials, None)
            raise ErroAutenticacao("token invalido ou expirado")
        return par[0]
