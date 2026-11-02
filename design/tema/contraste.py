"""
Verificação de contraste (WCAG 2.1) dos pares de cor usados no tema.

    python -m design.tema.contraste      (a partir da pasta do projeto)
    python tema/contraste.py             (a partir de design/)

Sai com código 1 se algum par ficar abaixo do mínimo.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import tokens  # type: ignore
else:
    from . import tokens


def _lum(hexa: str) -> float:
    hexa = hexa.lstrip("#")
    canais = [int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def razao(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (frente, fundo, mínimo, descrição)
PARES = [
    ("texto", "fundo", 4.5, "texto sobre fundo"),
    ("texto", "superficie", 4.5, "texto sobre cartão"),
    ("texto_secundario", "superficie", 4.5, "texto secundário"),
    ("texto_secundario", "fundo", 4.5, "texto secundário sobre fundo"),
    ("texto_terciario", "superficie", 4.5, "legenda/unidade"),
    ("texto_terciario", "superficie_alt", 4.5, "unidade no cabeçalho da tabela"),
    ("texto_terciario", "fundo", 4.5, "legenda sobre fundo"),
    ("texto_sobre_primaria", "primaria", 4.5, "botão primário"),
    ("texto_sobre_primaria", "primaria_hover", 4.5, "botão primário (hover)"),
    ("primaria_texto", "superficie", 4.5, "link/texto de ação"),
    ("primaria_texto", "primaria_suave", 4.5, "item de navegação ativo"),
    ("texto", "selecao", 4.5, "linha selecionada"),
    ("sucesso", "sucesso_suave", 4.5, "selo sucesso"),
    ("alerta", "alerta_suave", 4.5, "selo alerta"),
    ("erro", "erro_suave", 4.5, "selo erro"),
    ("info", "info_suave", 4.5, "selo info"),
    ("neutro", "neutro_suave", 4.5, "selo neutro"),
    ("erro", "superficie", 4.5, "mensagem de erro"),
    ("sucesso", "superficie", 4.5, "texto de sucesso"),
    ("alerta", "superficie", 4.5, "texto de alerta"),
    ("superficie", "erro", 4.5, "selo erro sólido / botão perigo"),
    ("borda_controle", "superficie", 3.0, "contorno de campo"),
    ("foco", "superficie", 3.0, "anel de foco"),
    ("foco", "fundo", 3.0, "anel de foco sobre fundo"),
]


def relatorio() -> tuple[list[tuple], bool]:
    linhas, ok = [], True
    for modo in tokens.MODOS:
        c = tokens.cores(modo)
        for frente, fundo, minimo, desc in PARES:
            r = razao(c[frente], c[fundo])
            passou = r >= minimo
            ok &= passou
            linhas.append((modo, desc, frente, fundo, c[frente], c[fundo], r, minimo, passou))
        g = tokens.cores_grafico(modo)
        for i, cor in enumerate(g["categoricas"]):
            r = razao(cor, g["fundo_eixos"])
            passou = r >= 3.0
            ok &= passou
            linhas.append((modo, f"série {i + 1} do gráfico", f"categoricas[{i}]", "fundo_eixos",
                           cor, g["fundo_eixos"], r, 3.0, passou))
    return linhas, ok


if __name__ == "__main__":
    linhas, ok = relatorio()
    for modo, desc, f, b, cf, cb, r, m, p in linhas:
        print(f"{modo:6} {'OK ' if p else 'FALHA'} {r:5.2f}:1 (mín {m}) {desc:34} {f}={cf} / {b}={cb}")
    sys.exit(0 if ok else 1)
