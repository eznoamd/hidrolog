#!/usr/bin/env python3
"""
Gera a versão da logo para o tema escuro: os pixels neutros e escuros (letreiro
em grafite ou preto) passam para um tom claro; as partes coloridas mantêm as
cores exatas, e o alfa de cada pixel é mantido (bordas suavizadas continuam
suaves). Funciona bem com logos de letreiro escuro sobre fundo transparente.

    venv/bin/python gerar_logo_escura.py <pasta de marca>
    # lê <pasta>/logo.png e grava <pasta>/logo-escura.png
"""

import colorsys
from pathlib import Path

from PIL import Image

CLARO = (0xE6, 0xE8, 0xEB)      # mesmo tom do texto principal do tema escuro


def eh_letreiro(r: int, g: int, b: int) -> bool:
    _, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return s < 0.12 and l < 0.6


def gerar(origem: Path, destino: Path) -> Path:
    im = Image.open(origem).convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a and eh_letreiro(r, g, b):
                px[x, y] = CLARO + (a,)
    im.save(destino)
    return destino


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("uso: gerar_logo_escura.py <pasta de marca com logo.png>")
    pasta = Path(sys.argv[1])
    print(gerar(pasta / "logo.png", pasta / "logo-escura.png"))
