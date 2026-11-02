"""Camada 1 da ingestao: ABRIR o envio e montar a arvore de arquivos.

Origens: pasta local, .zip, .rar, arquivos soltos ou partes de um upload
multipart, todas juntas num envio. Um .zip dentro de outro e aberto tambem,
ate 2 niveis (o compactado enviado e o nivel 1). Nada e extraido para o
disco (so um zip interno vai para um temporario, porque o zipfile precisa
de um arquivo com seek). A arvore so tem nomes e tamanhos: o conteudo e
lido quando o plugin pede (hidrolog_nucleo.plugin.ArquivoArvore).

Protecoes (as mesmas para dados e para os pacotes de plugin):
- path traversal: caminhos absolutos, com letra de unidade ou com ".." sao
  rejeitados (ErroEnvio), mesmo que nada seja gravado com esse nome;
- zip bomb: cada arquivo lido inteiro (ArquivoArvore.ler) tem no maximo
  max_arquivo_leitura bytes, e o total lido num envio (inteiro ou em fluxo)
  tem limite (max_descompactado), contado sobre os bytes reais;
- numero de arquivos limitado (max_arquivos).
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
import zlib
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Optional, Union

from hidrolog_nucleo.plugin import ArquivoArvore, ArvoreArquivos

from ..config import Configuracao
from .erros import ErroEnvio, ErroRarSemFerramenta, LimiteExcedido

_ASSINATURA_ZIP = (b"PK\x03\x04", b"PK\x05\x06")
_ASSINATURA_RAR = b"Rar!\x1a\x07"
_LETRA_UNIDADE = re.compile(r"^[A-Za-z]:")
NIVEIS_ZIP = 2          # zip enviado (1) + zip dentro dele (2)
_ERROS_DESCOMPACTAR = (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError)

INSTRUCAO_RAR = (
    "Para ler .rar comprimido instale um destes programas: unrar "
    "(sudo apt install unrar), unar (sudo apt install unar) ou bsdtar "
    "(sudo apt install libarchive-tools). No Windows, o UnRAR.exe do WinRAR "
    "no PATH. O 7z do Debian/Ubuntu nao serve: vem sem o codec RAR "
    "(precisaria do pacote 7zip-rar). Outra saida: enviar o SD como .zip ou pasta."
)


# ============================================================================ limites

class Contador:
    """Soma os bytes lidos e o numero de arquivos de um envio inteiro."""

    def __init__(self, config: Configuracao):
        self.config = config
        self.bytes = 0
        self.arquivos = 0

    def contar_arquivo(self) -> None:
        self.arquivos += 1
        if self.arquivos > self.config.max_arquivos:
            raise LimiteExcedido(f"mais de {self.config.max_arquivos} arquivos no envio")

    def somar(self, n: int) -> None:
        self.bytes += n
        if self.bytes > self.config.max_descompactado:
            raise LimiteExcedido(
                f"envio passa de {self.config.max_descompactado // (1024 * 1024)} MB descompactados")

    def ler(self, arquivo: BinaryIO, caminho: str) -> bytes:
        limite = self.config.max_arquivo_leitura
        try:
            dados = arquivo.read(limite + 1)
        except _ERROS_DESCOMPACTAR as erro:
            raise ErroEnvio(f"{caminho}: nao foi possivel descompactar ({erro})") from erro
        if len(dados) > limite:
            raise LimiteExcedido(f"{caminho}: arquivo maior que {limite} bytes (leia em fluxo com abrir/linhas)")
        self.somar(len(dados))
        return dados

    def fluxo(self, bruto: BinaryIO, caminho: str) -> BinaryIO:
        return io.BufferedReader(_FluxoContado(bruto, self, caminho))


class _FluxoContado(io.RawIOBase):
    """Fluxo que soma os bytes lidos no limite total do envio."""

    def __init__(self, bruto: BinaryIO, contador: Contador, caminho: str):
        super().__init__()
        self._bruto = bruto
        self._contador = contador
        self._caminho = caminho

    def readable(self) -> bool:
        return True

    def readinto(self, destino) -> int:
        try:
            dados = self._bruto.read(len(destino))
        except _ERROS_DESCOMPACTAR as erro:
            raise ErroEnvio(f"{self._caminho}: nao foi possivel descompactar ({erro})") from erro
        n = len(dados)
        destino[:n] = dados
        self._contador.somar(n)
        return n

    def close(self) -> None:
        try:
            self._bruto.close()
        finally:
            super().close()


# ============================================================================ nomes

def normalizar_caminho(nome: str) -> str:
    """Caminho relativo com "/" (aceita "\\" do Windows). Rejeita caminho
    absoluto, letra de unidade e "..". """
    nome = (nome or "").replace("\\", "/")
    if nome.startswith("/") or _LETRA_UNIDADE.match(nome):
        raise ErroEnvio(f"caminho absoluto nao permitido: {nome!r}")
    partes = [p for p in nome.split("/") if p not in ("", ".")]
    if ".." in partes:
        raise ErroEnvio(f"caminho com '..' nao permitido: {nome!r}")
    return "/".join(partes)


def _nome_zip(info: zipfile.ZipInfo) -> str:
    """Sem a flag UTF-8, o zipfile decodifica o nome em cp437. ZIPs do
    Windows em portugues costumam estar em cp850, e alguns programas gravam
    UTF-8 sem marcar a flag: tenta os dois."""
    if info.flag_bits & 0x800 or info.filename.isascii():
        return info.filename
    bruto = info.filename.encode("cp437")
    for codificacao in ("utf-8", "cp850"):
        try:
            return bruto.decode(codificacao)
        except UnicodeDecodeError:
            continue
    return info.filename


def tipo_do_arquivo(nome: str, inicio: bytes = b"") -> str:
    """zip, rar ou arquivo (pela assinatura, e na falta dela pela extensao)."""
    if inicio.startswith(_ASSINATURA_ZIP):
        return "zip"
    if inicio.startswith(_ASSINATURA_RAR):
        return "rar"
    sufixo = PurePosixPath(nome.replace("\\", "/")).suffix.lower()
    if sufixo in (".zip", ".rar"):
        return sufixo[1:]
    return "arquivo"


# ============================================================================ RAR

@lru_cache(maxsize=1)
def suporte_rar() -> tuple[Optional[str], str]:
    """(programa, mensagem). programa e None se nenhum programa que o
    rarfile usa consegue descompactar RAR neste sistema. RAR "armazenado"
    (sem compressao) e lido pelo proprio rarfile, sem programa."""
    import rarfile

    for programa, opcao in (("unrar", "unrar"), ("unar", "unar"), ("bsdtar", "bsdtar")):
        if shutil.which(programa):
            _configurar_rarfile(rarfile, opcao)
            return programa, f"RAR descompactado com {programa}"
    for programa, opcao in (("7z", "sevenzip"), ("7zz", "sevenzip2")):
        if shutil.which(programa) and _7z_tem_codec_rar(programa):
            _configurar_rarfile(rarfile, opcao)
            return programa, f"RAR descompactado com {programa}"
    return None, "nenhum programa para descompactar RAR. " + INSTRUCAO_RAR


def _configurar_rarfile(rarfile, opcao: str) -> None:
    opcoes = {o: o == opcao for o in ("unrar", "unar", "bsdtar", "sevenzip", "sevenzip2")}
    try:
        rarfile.tool_setup(force=True, **opcoes)
    except rarfile.RarCannotExec:
        pass


def _7z_tem_codec_rar(programa: str) -> bool:
    try:
        saida = subprocess.run([programa, "i"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    codecs = saida.split("Codecs:", 1)[-1] if "Codecs:" in saida else ""
    return bool(re.search(r"\bRar[1-5]?\b", codecs))


# ============================================================================ arquivos da arvore

class _ArquivoZip(ArquivoArvore):
    def __init__(self, caminho: str, arquivo_zip: zipfile.ZipFile, info: zipfile.ZipInfo):
        super().__init__(caminho, info.file_size)
        self._zip = arquivo_zip
        self._info = info

    def _abrir_bruto(self) -> BinaryIO:
        try:
            return self._zip.open(self._info)
        except _ERROS_DESCOMPACTAR as erro:
            raise ErroEnvio(f"{self.caminho}: nao foi possivel descompactar ({erro})") from erro


class _ArquivoRar(ArquivoArvore):
    def __init__(self, caminho: str, arquivo_rar, info, nome_rar: str):
        super().__init__(caminho, info.file_size)
        self._rar = arquivo_rar
        self._info = info
        self._nome_rar = nome_rar

    def _abrir_bruto(self) -> BinaryIO:
        import rarfile

        if self._info.compress_type != rarfile.RAR_M0 and suporte_rar()[0] is None:
            raise ErroRarSemFerramenta(f"{self._nome_rar}: {suporte_rar()[1]}")
        try:
            return self._rar.open(self._info)
        except rarfile.RarCannotExec as erro:
            raise ErroRarSemFerramenta(f"{self._nome_rar}: {INSTRUCAO_RAR}") from erro
        except (rarfile.Error, OSError) as erro:
            raise ErroEnvio(f"{self._nome_rar}/{self.caminho}: nao foi possivel descompactar ({erro}). "
                            f"{INSTRUCAO_RAR}") from erro


class _ArquivoDisco(ArquivoArvore):
    def __init__(self, caminho: str, local: Path):
        super().__init__(caminho, local.stat().st_size)
        self._local = local

    def _abrir_bruto(self) -> BinaryIO:
        return open(self._local, "rb")


class _SemFechar(io.RawIOBase):
    """Fluxo de um upload: le do inicio e nao fecha o arquivo de quem chamou."""

    def __init__(self, arquivo: BinaryIO):
        super().__init__()
        self._arquivo = arquivo
        arquivo.seek(0)

    def readable(self) -> bool:
        return True

    def readinto(self, destino) -> int:
        dados = self._arquivo.read(len(destino))
        destino[:len(dados)] = dados
        return len(dados)


class _ArquivoParte(ArquivoArvore):
    def __init__(self, caminho: str, arquivo: BinaryIO):
        super().__init__(caminho, None)
        self._arquivo = arquivo

    def _abrir_bruto(self) -> BinaryIO:
        return io.BufferedReader(_SemFechar(self._arquivo))


# ============================================================================ abertura do envio

class Abertura:
    """Abre os itens de um envio e monta UMA arvore com todos os arquivos.
    Mantem os compactados abertos ate fechar() (o plugin le quando quiser).

        with Abertura(config) as ab:
            ab.adicionar_caminho("/media/SD")
            ab.adicionar_parte("SD.zip", fluxo)
            ab.arvore  -> ArvoreArquivos
    """

    def __init__(self, config: Configuracao):
        self.config = config
        self.contador = Contador(config)
        self.arvore = ArvoreArquivos()
        self.tipos: list[str] = []
        self.nomes: list[str] = []
        self.tem_pasta = False
        self._abertos: list = []
        self._temp: Optional[tempfile.TemporaryDirectory] = None
        self._n_temp = 0

    def __enter__(self) -> "Abertura":
        return self

    def __exit__(self, *_):
        self.fechar()
        return False

    def fechar(self) -> None:
        for aberto in reversed(self._abertos):
            try:
                aberto.close()
            except Exception:  # noqa: BLE001
                pass
        self._abertos.clear()
        if self._temp is not None:
            self._temp.cleanup()
            self._temp = None

    def _novo_temp(self, sufixo: str) -> Path:
        if self._temp is None:
            self._temp = tempfile.TemporaryDirectory(prefix="hidrolog_envio_")
        self._n_temp += 1
        return Path(self._temp.name) / f"t{self._n_temp}{sufixo}"

    def _acrescentar(self, arquivo: ArquivoArvore) -> None:
        self.contador.contar_arquivo()
        arquivo._contador = self.contador
        self.arvore.arquivos.append(arquivo)

    # ------------------------------------------------------------------ itens
    def adicionar_caminho(self, caminho: Union[str, Path]) -> str:
        """Caminho local: pasta (ex. o SD inteiro), .zip, .rar ou arquivo solto.
        Devolve o tipo ("pasta", "zip", "rar" ou "arquivos")."""
        caminho = Path(caminho).expanduser()
        if not caminho.exists():
            raise ErroEnvio(f"caminho nao encontrado: {caminho}")
        self.nomes.append(str(caminho))
        if caminho.is_dir():
            tipo = "pasta"
            self._pasta(caminho)
        else:
            with open(caminho, "rb") as f:
                tipo = tipo_do_arquivo(caminho.name, f.read(8))
            if tipo == "zip":
                self._zip(caminho, caminho.name, "", 1)
            elif tipo == "rar":
                self._rar(caminho, caminho.name, "")
            else:
                tipo = "arquivos"
                self._acrescentar(_ArquivoDisco(normalizar_caminho(caminho.name), caminho))
        self.tipos.append(tipo)
        return tipo

    def adicionar_parte(self, nome: str, arquivo: BinaryIO) -> str:
        """Uma parte de um upload multipart (o nome pode trazer o caminho
        relativo, ex. "2026102116/20261021160000.txt")."""
        caminho = normalizar_caminho(nome)
        if not caminho:
            raise ErroEnvio("parte do upload sem nome de arquivo")
        self.nomes.append(nome)
        self.tem_pasta = self.tem_pasta or "/" in caminho
        inicio = arquivo.read(8)
        arquivo.seek(0)
        tipo = tipo_do_arquivo(caminho, inicio)
        if tipo == "zip":
            self._zip(arquivo, caminho, "", 1)
        elif tipo == "rar":
            # o rarfile precisa de um arquivo no disco para chamar o unrar
            destino = self._novo_temp(".rar")
            with open(destino, "wb") as f:
                shutil.copyfileobj(arquivo, f)
            self._rar(destino, caminho, "")
        else:
            tipo = "arquivos"
            self._acrescentar(_ArquivoParte(caminho, arquivo))
        self.tipos.append(tipo)
        return tipo

    # ------------------------------------------------------------------ origens
    def _pasta(self, pasta: Path) -> None:
        """Percorre a pasta (sem seguir links simbolicos). Um .zip/.rar dentro
        da pasta e aberto (nivel 1)."""
        for raiz, pastas, arquivos in os.walk(pasta):
            pastas.sort()
            for nome in sorted(arquivos):
                local = Path(raiz) / nome
                if local.is_symlink():
                    continue
                caminho = local.relative_to(pasta).as_posix()
                sufixo = local.suffix.lower()
                if sufixo == ".zip" and zipfile.is_zipfile(local):
                    self._zip(local, caminho, caminho + "/", 1)
                elif sufixo == ".rar":
                    self._rar(local, caminho, caminho + "/")
                else:
                    self._acrescentar(_ArquivoDisco(caminho, local))

    def _zip(self, origem, nome: str, prefixo: str, nivel: int) -> None:
        try:
            arquivo_zip = zipfile.ZipFile(origem)
        except zipfile.BadZipFile as erro:
            raise ErroEnvio(f"{nome or 'arquivo'}: ZIP invalido ({erro})") from erro
        self._abertos.append(arquivo_zip)
        for info in arquivo_zip.infolist():
            caminho = normalizar_caminho(_nome_zip(info))
            if info.is_dir() or not caminho:
                continue
            completo = prefixo + caminho
            if nivel < NIVEIS_ZIP and caminho.lower().endswith(".zip"):
                interno = self._extrair_zip_interno(arquivo_zip, info, completo)
                if interno is not None:
                    self._zip(interno, completo, completo + "/", nivel + 1)
                    continue
            self._acrescentar(_ArquivoZip(completo, arquivo_zip, info))

    def _extrair_zip_interno(self, arquivo_zip: zipfile.ZipFile, info, caminho: str) -> Optional[Path]:
        """Copia um zip interno para um temporario (o zipfile precisa de seek),
        contando os bytes no limite do envio. None se nao for zip de verdade."""
        destino = self._novo_temp(".zip")
        try:
            with arquivo_zip.open(info) as origem, open(destino, "wb") as saida:
                while True:
                    bloco = origem.read(1024 * 1024)
                    if not bloco:
                        break
                    self.contador.somar(len(bloco))
                    saida.write(bloco)
        except _ERROS_DESCOMPACTAR as erro:
            raise ErroEnvio(f"{caminho}: nao foi possivel descompactar ({erro})") from erro
        if not zipfile.is_zipfile(destino):
            destino.unlink()
            return None
        return destino

    def _rar(self, caminho_rar: Path, nome: str, prefixo: str) -> None:
        import rarfile

        try:
            arquivo_rar = rarfile.RarFile(str(caminho_rar))
        except (rarfile.Error, OSError) as erro:
            raise ErroEnvio(f"{nome}: RAR invalido ({erro})") from erro
        self._abertos.append(arquivo_rar)
        if arquivo_rar.needs_password():
            raise ErroEnvio(f"{nome}: RAR com senha nao e suportado")
        for info in arquivo_rar.infolist():
            caminho = normalizar_caminho(info.filename)
            if info.is_dir() or not caminho:
                continue
            self._acrescentar(_ArquivoRar(prefixo + caminho, arquivo_rar, info, nome))
