"""Interface do termometro: uma aba com a serie de temperatura. So este
modulo importa PySide6/matplotlib (o nucleo o importa sob demanda)."""

from hidrolog_nucleo.plugin import Aba


def _criar_serie(contexto):
    from matplotlib.figure import Figure
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from design.componentes import EstadoVazio, FiguraIncorporada

    class AbaSerie(QWidget):
        def __init__(self, contexto):
            super().__init__()
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            self.figura = FiguraIncorporada(titulo="Temperatura", altura_minima=420)
            self.vazio = EstadoVazio("Nenhuma leitura neste período", "Importe um CSV do termômetro.", "gauge")
            lay.addWidget(self.figura)
            lay.addWidget(self.vazio)
            self.atualizar(contexto)

        def atualizar(self, contexto):
            leituras = contexto.consultas.buscar(contexto.usuario, contexto.equipamento.id,
                                                 contexto.inicio, contexto.fim)
            suspeitas = contexto.suspeitas()
            if contexto.ocultar_suspeitas:
                leituras = [l for l in leituras if l[0] not in suspeitas]
            self.vazio.setVisible(not leituras)
            self.figura.setVisible(bool(leituras))
            if not leituras:
                return
            fig = Figure()
            ax = fig.add_subplot()
            ax.plot([l[0] for l in leituras], [l[1] for l in leituras], label="temperatura")
            marcadas = [l for l in leituras if l[0] in suspeitas]
            if marcadas:
                ax.scatter([l[0] for l in marcadas], [l[1] for l in marcadas], label="suspeita", zorder=5)
                ax.legend()
            ax.set_ylabel("°C")
            self.figura.definir_figura(fig)

    return AbaSerie(contexto)


ABAS = [Aba("serie", "Temperatura", _criar_serie, icone="chart-line", descricao="Série de temperatura do período.")]
