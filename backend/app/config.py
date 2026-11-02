"""Configuracao, lida de variaveis de ambiente (todas opcionais)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

NOME_APP = "Hidrolog"
MB = 1024 * 1024


def diretorio_dados_padrao() -> Path:
    """Diretorio de dados do usuario, conforme o sistema:
    Linux ~/.local/share (ou $XDG_DATA_HOME), Windows %LOCALAPPDATA%,
    macOS ~/Library/Application Support."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / NOME_APP


def instituicao_da_instalacao(diretorio_dados: Optional[Path]) -> str:
    """Laboratorio e instituicao da pasta de marca da instalacao
    (HIDROLOG_MARCA_DIR ou <dados>/marca/marca.toml), para metadados das
    exportacoes, ex. "Laboratorio X (LAB); Universidade Y (UNIV)". "" sem pasta."""
    pasta = os.environ.get("HIDROLOG_MARCA_DIR") or (diretorio_dados / "marca" if diretorio_dados else None)
    arquivo = Path(pasta) / "marca.toml" if pasta else None
    if arquivo is None or not arquivo.is_file():
        return ""
    try:
        import tomllib
    except ModuleNotFoundError:          # Python 3.10
        import tomli as tomllib
    dados = tomllib.loads(arquivo.read_text(encoding="utf-8-sig"))  # aceita o BOM do Bloco de Notas
    partes = []
    for secao in ("laboratorio", "instituicao"):
        nome, sigla = dados.get(secao, {}).get("nome"), dados.get(secao, {}).get("sigla")
        if nome or sigla:
            partes.append(f"{nome} ({sigla})" if nome and sigla else (nome or sigla))
    return "; ".join(partes)


@dataclass(frozen=True)
class Configuracao:
    database_url: str
    max_descompactado: int        # bytes lidos de arquivos de dados num envio (protege contra zip bomb)
    max_arquivo_leitura: int      # bytes de um arquivo de dados (uma leitura costuma ter poucos kB)
    max_arquivos: int             # entradas num arquivo compactado / partes num upload
    processos: int                # processos para interpretar os arquivos (1 = sem paralelismo)
    diretorio_dados: Optional[Path] = None   # banco, log, pasta de plugins (None: sem pasta de plugins)

    @property
    def diretorio_plugins(self) -> Optional[Path]:
        """<dados do app>/plugins: onde o gerenciador instala os plugins."""
        return self.diretorio_dados / "plugins" if self.diretorio_dados is not None else None

    @classmethod
    def do_ambiente(cls) -> "Configuracao":
        url = os.environ.get("DATABASE_URL")
        pasta = Path(os.environ.get("HIDROLOG_DADOS_DIR") or diretorio_dados_padrao())
        pasta.mkdir(parents=True, exist_ok=True)
        if not url:
            url = f"sqlite:///{pasta / 'hidrolog.db'}"
        return cls(
            database_url = url,
            max_descompactado = int(os.environ.get("HIDROLOG_MAX_DESCOMPACTADO_MB", "2048")) * MB,
            max_arquivo_leitura = int(os.environ.get("HIDROLOG_MAX_ARQUIVO_KB", "1024")) * 1024,
            max_arquivos = int(os.environ.get("HIDROLOG_MAX_ARQUIVOS", "500000")),
            # no app empacotado (PyInstaller), um processo so por padrao: os processos
            # filhos do pool sao novas execucoes do .exe
            processos = int(os.environ.get("HIDROLOG_PROCESSOS",
                                           "1" if getattr(sys, "frozen", False) else str(min(4, os.cpu_count() or 1)))),
            diretorio_dados = pasta,
        )
