"""Gera um .rar (formato RAR 4) com arquivos "armazenados" (sem
compressao), para testar sem o programa rar, que nao e livre. O rarfile le
esse tipo de entrada sozinho, sem unrar. Os nomes usam "\\", como o WinRAR
no Windows."""

import struct
import zlib

_MARCA = b"Rar!\x1a\x07\x00"


def _bloco(tipo: int, flags: int, corpo: bytes) -> bytes:
    cabecalho = struct.pack("<BHH", tipo, flags, 7 + len(corpo)) + corpo
    crc = zlib.crc32(cabecalho) & 0xFFFF
    return struct.pack("<H", crc) + cabecalho


def criar_rar(arquivos: dict[str, bytes], metodo: int = 0x30) -> bytes:
    """arquivos: {nome com "\\" ou "/": conteudo}. metodo 0x30 = armazenado;
    outro valor so serve para simular um RAR comprimido (dados invalidos)."""
    saida = [_MARCA, _bloco(0x73, 0, b"\x00" * 6)]
    dos_hora = (2026 - 1980) << 25 | 10 << 21 | 29 << 16
    for nome, conteudo in arquivos.items():
        nome_bytes = nome.replace("/", "\\").encode("ascii")
        corpo = struct.pack(
            "<IIBIIBBHI",
            len(conteudo), len(conteudo), 2,       # pack, unpack, host Windows
            zlib.crc32(conteudo), dos_hora,
            29, metodo, len(nome_bytes), 0x20,
        ) + nome_bytes
        saida.append(_bloco(0x74, 0x8000, corpo))
        saida.append(conteudo)
    saida.append(_bloco(0x7B, 0x4000, b""))
    return b"".join(saida)
