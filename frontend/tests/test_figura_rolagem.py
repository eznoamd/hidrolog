"""Com o ponteiro em cima de um gráfico, a roda do mouse rola a página."""

from matplotlib.figure import Figure
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QScrollArea, QVBoxLayout, QWidget

from design.componentes import FiguraIncorporada


def test_roda_sobre_o_grafico_rola_a_pagina(qapp, qtbot):
    conteudo = QWidget()
    lay = QVBoxLayout(conteudo)
    fig = Figure()
    fig.subplots().plot([0, 1, 2], [1, 3, 2])
    figura = FiguraIncorporada(fig, "Gráfico", altura_minima=600)
    lay.addWidget(figura)
    lay.addSpacing(1500)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(conteudo)
    area.resize(600, 400)
    qtbot.addWidget(area)
    area.show()
    qtbot.waitExposed(area)
    barra = area.verticalScrollBar()
    assert barra.value() == 0
    canvas = figura.canvas
    centro = QPointF(canvas.width() / 2, canvas.height() / 2)
    evento = QWheelEvent(centro, QPointF(canvas.mapToGlobal(centro.toPoint())), QPoint(0, 0), QPoint(0, -120),
                         Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(canvas, evento)
    assert barra.value() > 0


def test_trocar_a_figura_nao_duplica_a_barra(qtbot):
    """Trocar a figura (ex.: mudar o período) deixa uma barra de ferramentas só, na hora."""
    from matplotlib.figure import Figure

    from design.componentes import FiguraIncorporada
    from design.componentes.figura import _BarraGrafico

    f = FiguraIncorporada(titulo="Série")
    qtbot.addWidget(f)
    f.show()
    for _ in range(3):
        fig = Figure()
        fig.add_subplot().plot([0, 1], [0, 1])
        f.definir_figura(fig)
    # logo depois da troca, antes do ciclo de eventos (quando o deleteLater ainda não rodou),
    # só a barra nova pode estar à mostra; as antigas já saíram
    no_layout = [b for b in f.findChildren(_BarraGrafico) if f._topo.indexOf(b) >= 0]
    assert no_layout == [f.barra]
    assert all(b.isHidden() for b in f.findChildren(_BarraGrafico) if b is not f.barra)
