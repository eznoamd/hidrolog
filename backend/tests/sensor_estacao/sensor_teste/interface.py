"""Uma aba da estação de teste: a tabela de leituras do período (só este
módulo importa PySide6)."""

from hidrolog_nucleo.plugin import Aba


def _criar_leituras(contexto):
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from design.componentes import Coluna, TabelaFiltravel

    class AbaLeituras(QWidget):
        def __init__(self, contexto):
            super().__init__()
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
            self.tabela = TabelaFiltravel([
                Coluna("tempo", "Tempo", "data_hora", largura=150), Coluna("chuva", "Chuva (mm/h)", "numero"),
                Coluna("temperatura", "Temperatura (°C)", "numero"), Coluna("status", "Status", "inteiro"),
            ], mostrar_busca=False, titulo_vazio="Nenhuma leitura neste período", icone_vazio="gauge")
            lay.addWidget(self.tabela)
            self.atualizar(contexto)

        def atualizar(self, contexto):
            leituras = contexto.consultas.buscar_leituras(contexto.usuario, contexto.equipamento.id,
                                                          contexto.inicio, contexto.fim)
            if contexto.ocultar_suspeitas:
                suspeitas = contexto.suspeitas()
                leituras = [l for l in leituras if l["tempo"] not in suspeitas]
            self.leituras = leituras
            self.tabela.definir_linhas(leituras)

    return AbaLeituras(contexto)


ABAS = [Aba("leituras", "Leituras", _criar_leituras, icone="gauge", descricao="Leituras do período.")]
