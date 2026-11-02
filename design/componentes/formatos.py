"""Formatação pt-BR de números, datas e períodos (usada por tabelas e cartões)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from ..tema import tokens

TRACO = "—"  # valor ausente


def numero(valor, casas: int = 1, unidade: str | None = None) -> str:
    """1234.5 -> '1.234,5'; None/NaN -> '—'. Com unidade: '12,3 mm'."""
    if valor is None or (isinstance(valor, float) and valor != valor):
        return TRACO
    texto = f"{valor:,.{casas}f}"
    texto = texto.replace(",", "\x00").replace(".", tokens.FORMATO["separador_decimal"])
    texto = texto.replace("\x00", tokens.FORMATO["separador_milhar"])
    if texto.startswith("-"):
        texto = "−" + texto[1:]  # sinal de menos tipográfico
    return f"{texto} {unidade}" if unidade else texto


def inteiro(valor, unidade: str | None = None) -> str:
    return numero(valor, 0, unidade)


def data(valor: date | datetime | None) -> str:
    return valor.strftime(tokens.FORMATO["data"]) if valor else TRACO


def data_hora(valor: datetime | None, segundos: bool = False) -> str:
    if not valor:
        return TRACO
    return valor.strftime(tokens.FORMATO["data_hora_seg" if segundos else "data_hora"])


def periodo(inicio: datetime | None, fim: datetime | None) -> str:
    """'03/10/2026 14:00 – 05/10/2026 08:30' (mesmo dia: '03/10/2026 14:00 – 18:30')."""
    if not inicio or not fim:
        return TRACO
    if inicio.date() == fim.date():
        return f"{data_hora(inicio)} – {fim.strftime(tokens.FORMATO['hora'])}"
    return f"{data_hora(inicio)} – {data_hora(fim)}"


def duracao(delta: timedelta | None) -> str:
    """timedelta -> '2 d 4 h', '3 h 15 min', '45 min'."""
    if delta is None:
        return TRACO
    minutos = int(delta.total_seconds() // 60)
    d, resto = divmod(minutos, 1440)
    h, m = divmod(resto, 60)
    if d:
        return f"{d} d {h} h" if h else f"{d} d"
    if h:
        return f"{h} h {m:02d} min" if m else f"{h} h"
    return f"{m} min"
