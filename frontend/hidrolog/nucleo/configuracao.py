"""Diretório de dados, log em arquivo e preferências (QSettings)."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QSettings

NOME_LOG = "hidrolog.log"
NOME_PREFERENCIAS = "hidrolog-interface.ini"
log = logging.getLogger("hidrolog")


def diretorio_dados() -> Path:
    """Mesmo diretório do banco do backend: HIDROLOG_DADOS_DIR ou o padrão do sistema."""
    from app.config import diretorio_dados_padrao

    pasta = Path(os.environ.get("HIDROLOG_DADOS_DIR") or diretorio_dados_padrao())
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def diretorio_marca() -> Path:
    """Pasta de marca da instalação (marca.toml + logos): HIDROLOG_MARCA_DIR ou
    <dados do app>/marca. Sem ela, o app fica genérico (ver design/tema/marca.py)."""
    return Path(os.environ.get("HIDROLOG_MARCA_DIR") or diretorio_dados() / "marca")


def caminho_log() -> Path:
    return diretorio_dados() / NOME_LOG


def configurar_log() -> Path:
    """Log em arquivo (com rotação) no diretório de dados. Os detalhes dos
    erros (tracebacks) vão só para cá; a tela mostra a mensagem amigável."""
    destino = caminho_log()
    raiz = logging.getLogger("hidrolog")
    for h in list(raiz.handlers):
        if getattr(h, "_hidrolog", False):
            raiz.removeHandler(h)
            h.close()
    manipulador = RotatingFileHandler(destino, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8")
    manipulador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    manipulador._hidrolog = True  # type: ignore[attr-defined]
    raiz.addHandler(manipulador)
    raiz.setLevel(logging.INFO)
    return destino


def preferencias() -> QSettings:
    """Preferências da interface (tema etc.), num .ini ao lado do banco."""
    return QSettings(str(diretorio_dados() / NOME_PREFERENCIAS), QSettings.Format.IniFormat)


def tema_salvo() -> str:
    modo = preferencias().value("interface/tema", "claro")
    return modo if modo in ("claro", "escuro") else "claro"


def salvar_tema(modo: str) -> None:
    p = preferencias()
    p.setValue("interface/tema", modo)
    p.sync()
