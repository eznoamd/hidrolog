"""Formulário gerado a partir de uma ficha declarativa (lista de campos).

Cada campo é um objeto com os atributos de `hidrolog_nucleo.plugin.Campo`
(chave, rotulo, tipo, unidade, opcoes, ajuda, somente_leitura, origem,
padrao): o componente não depende do backend. A validação é do backend; o
formulário só coleta o texto digitado e mostra os erros que voltarem.

    form = FormularioFicha(campos)
    form.definir_valores({"intervalo_esperado_s": 120})
    valores = form.valores()            # {chave: texto | bool | None}, só os editáveis
    form.mostrar_erros({"intervalo_esperado_s": "mínimo 10 s"})

tipo: texto | inteiro | decimal | booleano | data | escolha.
Campos somente leitura (ou preenchidos pelas leituras) aparecem como texto.
"""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ..tema import DIMENSAO, ESPACO, repolir
from . import formatos
from .base import rotulo


class FormularioFicha(QWidget):
    def __init__(self, campos, parent: QWidget | None = None, form: QFormLayout | None = None,
                 so_editaveis: bool = False, ajuda_como_dica: bool = False):
        """form: um QFormLayout de quem usa (ex. um diálogo) para pôr as linhas
        direto nele, alinhadas com os outros campos; sem ele, o próprio widget
        tem o formulário. remover() tira as linhas de um form externo.
        so_editaveis: omite os campos somente leitura e os preenchidos pelas
        leituras (num formulário de edição eles só ocupam espaço).
        ajuda_como_dica: a ajuda de cada campo vira dica (ao passar o mouse)
        em vez de texto embaixo do campo."""
        super().__init__(parent)
        self._ajuda_como_dica = ajuda_como_dica
        self.campos = [c for c in campos if self.editavel(c)] if so_editaveis else list(campos)
        self._externo = form is not None
        if form is None:
            form = QFormLayout(self)
            form.setContentsMargins(0, 0, 0, 0)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
            form.setFormAlignment(Qt.AlignmentFlag.AlignLeft)
            form.setHorizontalSpacing(ESPACO["lg"])
            form.setVerticalSpacing(ESPACO["md"])
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form = form
        self._rotulos: list[QWidget] = []
        self.widgets: dict[str, QWidget] = {}
        self._erros: dict[str, QLabel] = {}
        for campo in self.campos:
            self._adicionar(campo)

    @staticmethod
    def editavel(campo) -> bool:
        return not getattr(campo, "somente_leitura", False) and getattr(campo, "origem", None) is None

    def _adicionar(self, campo) -> None:
        r = rotulo(campo.rotulo, "rotulo_campo")
        if self.form.rowWrapPolicy() != QFormLayout.RowWrapPolicy.WrapAllRows:   # rótulo ao lado do campo
            r.setFixedHeight(DIMENSAO["altura_controle"])
        r.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        bloco = QVBoxLayout()
        bloco.setSpacing(ESPACO["xs"])
        linha = QHBoxLayout()
        linha.setSpacing(ESPACO["sm"])
        if not self.editavel(campo):
            w = rotulo(formatos.TRACO, None, mono=True)
            w.setMinimumHeight(DIMENSAO["altura_controle"])
            w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        elif campo.tipo == "booleano":
            w = QCheckBox("Sim")
        elif campo.tipo == "escolha":
            w = QComboBox()
            w.addItem(formatos.TRACO, None)
            for opcao in campo.opcoes:
                valor, texto = (opcao if isinstance(opcao, (tuple, list)) else (opcao, str(opcao)))
                w.addItem(str(texto), valor)
        else:
            w = QLineEdit()
            w.setPlaceholderText({"data": "dd/mm/aaaa", "inteiro": "número inteiro",
                                  "decimal": "número"}.get(campo.tipo, "opcional"))
            if getattr(campo, "padrao", None) is not None:
                w.setPlaceholderText(f"padrão: {self._texto(campo, campo.padrao)}")
        w.setAccessibleName(campo.rotulo)
        linha.addWidget(w, 1)
        if campo.unidade:
            linha.addWidget(rotulo(campo.unidade, "legenda"))
        bloco.addLayout(linha)
        ajuda = campo.ajuda
        if not self.editavel(campo) and getattr(campo, "origem", None) == "leituras" and not ajuda:
            ajuda = "Preenchido a partir das leituras."
        if ajuda and self._ajuda_como_dica:
            r.setToolTip(ajuda)
            w.setToolTip(ajuda)
        elif ajuda:
            r_ajuda = rotulo(ajuda, "legenda", quebra=True)
            r_ajuda.ensurePolished()
            # o QFormLayout não reserva a altura do texto quebrado: garante as linhas na largura mínima
            empilhado = self.form.rowWrapPolicy() == QFormLayout.RowWrapPolicy.WrapAllRows
            r_ajuda.setMinimumHeight(r_ajuda.heightForWidth(360 if empilhado else 300))
            bloco.addWidget(r_ajuda)
        erro = rotulo("", "erro", quebra=True)
        erro.hide()
        bloco.addWidget(erro)
        self.form.addRow(r, bloco)
        self._rotulos.append(r)
        self.widgets[campo.chave] = w
        self._erros[campo.chave] = erro

    def remover(self) -> None:
        """Tira do form externo as linhas que este formulário pôs lá."""
        if self._externo:
            for r in self._rotulos:
                self.form.removeRow(r)
        self._rotulos.clear()

        # ------------------------------------------------------------------ valores
    @staticmethod
    def _texto(campo, valor) -> str:
        if valor is None or valor == "":
            return ""
        if campo.tipo == "decimal" and isinstance(valor, (int, float)):
            return f"{float(valor):.6g}".replace(".", ",")
        if campo.tipo == "inteiro" and isinstance(valor, (int, float)):
            return str(int(valor))
        if campo.tipo == "data":
            try:
                return date.fromisoformat(str(valor)).strftime("%d/%m/%Y")
            except ValueError:
                return str(valor)
        if campo.tipo == "booleano":
            return "Sim" if valor else "Não"
        return str(valor)

    def definir_valores(self, valores: dict) -> None:
        for campo in self.campos:
            w = self.widgets[campo.chave]
            valor = (valores or {}).get(campo.chave)
            if isinstance(w, QLabel):
                w.setText(self._texto(campo, valor) or formatos.TRACO)
            elif isinstance(w, QCheckBox):
                w.setChecked(bool(valor))
            elif isinstance(w, QComboBox):
                w.setCurrentIndex(max(0, w.findData(valor)))
            else:
                w.setText(self._texto(campo, valor))

    def valores(self) -> dict:
        """Só os campos editáveis: texto digitado (vazio = None), bool ou a opção."""
        saida = {}
        for campo in self.campos:
            if not self.editavel(campo):
                continue
            w = self.widgets[campo.chave]
            if isinstance(w, QCheckBox):
                saida[campo.chave] = w.isChecked()
            elif isinstance(w, QComboBox):
                saida[campo.chave] = w.currentData()
            else:
                texto = w.text().strip()
                if campo.tipo == "data" and texto:
                    try:
                        texto = datetime.strptime(texto, "%d/%m/%Y").date().isoformat()
                    except ValueError:
                        pass          # o backend recusa com a mensagem
                saida[campo.chave] = texto or None
        return saida

    # ------------------------------------------------------------------ erros
    def mostrar_erros(self, erros: dict) -> bool:
        """Mostra as mensagens nos campos conhecidos. True se algum era daqui."""
        achou = False
        for chave, mensagem in (erros or {}).items():
            if chave in self.widgets:
                w = self.widgets[chave]
                w.setProperty("invalido", "true")
                repolir(w)
                self._erros[chave].setText(mensagem[:1].upper() + mensagem[1:])
                self._erros[chave].show()
                achou = True
        return achou

    def limpar_erros(self) -> None:
        for chave, w in self.widgets.items():
            w.setProperty("invalido", "false")
            repolir(w)
            self._erros[chave].hide()
