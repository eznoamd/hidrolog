"""Selo (badge) de status: perfis de usuário, status de sensor, situação de envio."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ..tema import PERFIS, TONS, repolir


class Selo(QLabel):
    """Pílula com texto curto e um tom semântico.

    tom: "neutro" | "info" | "sucesso" | "alerta" | "erro"
    solido: fundo cheio (para o caso mais grave de uma escala, ex.: status 3).
    """

    def __init__(self, texto: str = "", tom: str = "neutro", solido: bool = False,
                 dica: str | None = None, parent: QWidget | None = None):
        super().__init__(texto, parent)
        self.setProperty("papel", "selo")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        if dica:
            self.setToolTip(dica)
        self.definir(texto, tom, solido)

    def definir(self, texto: str | None = None, tom: str | None = None, solido: bool | None = None) -> None:
        if texto is not None:
            self.setText(texto)
            self.setAccessibleName(texto)
        if tom is not None:
            if tom not in TONS:
                raise ValueError(f"tom inválido: {tom!r}; use um de {TONS}")
            self.setProperty("tom", tom)
        if solido is not None:
            self.setProperty("solido", "true" if solido else "false")
        repolir(self)
        self.adjustSize()


def selo_perfil(perfil: str, parent: QWidget | None = None) -> Selo:
    """Selo padronizado para os perfis master / cadastro / leitura."""
    rotulo, tom = PERFIS.get(perfil, (perfil.capitalize(), "neutro"))
    return Selo(rotulo, tom, parent=parent)
