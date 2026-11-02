"""Tela de login."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ..tema import DIMENSAO, ESPACO, gerenciador, icone, repolir
from .base import Botao, Divisoria, rotulo
from .carregando import IndicadorCarregamento
from .dialogos import FaixaAviso
from ..tema.marca import marca_atual
from .logo import LogoInstituicao, LogoMarca


class TelaLogin(QWidget):
    """Login com usuário e senha. O front conecta `entrar(usuario, senha)`
    à autenticação e chama `mostrar_erro(...)` se falhar.

    Não há "esqueci a senha": quem redefine senhas é o perfil master.
    """

    entrar = Signal(str, str)

    def __init__(self, versao: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        m = marca_atual()
        self.setObjectName("Fundo")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        externo = QVBoxLayout(self)
        externo.setContentsMargins(ESPACO["xl"], ESPACO["xl"], ESPACO["xl"], ESPACO["xl"])
        externo.addStretch(1)

        cartao = QFrame()
        cartao.setProperty("papel", "cartao")
        cartao.setFixedSize(DIMENSAO["largura_login"], DIMENSAO["altura_login"])
        h = QHBoxLayout(cartao)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # --- painel da marca
        marca = QWidget()
        marca.setFixedWidth(400)
        vm = QVBoxLayout(marca)
        vm.setContentsMargins(ESPACO["xxl"] + 8, ESPACO["xxl"] + 8, ESPACO["xxl"], ESPACO["xl"])
        vm.setSpacing(ESPACO["md"])
        vm.addStretch(2)
        self.logo = LogoMarca(altura=DIMENSAO["altura_logo_login"], alinhamento=Qt.AlignmentFlag.AlignLeft)
        vm.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignLeft)
        if not self.logo.tem_imagem and m.laboratorio_completo:
            vm.addWidget(rotulo(m.laboratorio_completo, "secundario", quebra=True))
        vm.addSpacing(ESPACO["xxl"])
        vm.addWidget(Divisoria())
        vm.addSpacing(ESPACO["lg"])
        nome = rotulo(m.nome_app, "marca_app_login")
        nome.setAccessibleName(m.titulo_janela)
        vm.addWidget(nome)
        vm.addWidget(rotulo(m.descricao, "secundario", quebra=True))
        vm.addStretch(3)
        instituicao = QHBoxLayout()
        instituicao.setSpacing(ESPACO["md"])
        instituicao.addWidget(LogoInstituicao(altura=44))
        inst = rotulo(m.instituicao or "Instituição", "legenda", quebra=True)
        inst.setMinimumWidth(210)
        instituicao.addWidget(inst)
        instituicao.addStretch(1)
        vm.addLayout(instituicao)
        h.addWidget(marca)
        h.addWidget(Divisoria(vertical=True))

        # --- formulário
        form = QWidget()
        vf = QVBoxLayout(form)
        vf.setContentsMargins(ESPACO["xxxl"], ESPACO["xxl"], ESPACO["xxxl"], ESPACO["xl"])
        vf.setSpacing(ESPACO["xs"])
        vf.addStretch(2)
        vf.addWidget(rotulo("Entrar", "titulo_pagina"))
        vf.addWidget(rotulo("Use o usuário e a senha fornecidos pelo administrador do sistema.",
                            "secundario", quebra=True))
        vf.addSpacing(ESPACO["xl"])

        self.aviso = FaixaAviso(tom="erro")
        vf.addWidget(self.aviso)
        vf.addSpacing(ESPACO["xs"])

        vf.addWidget(rotulo("Usuário", "rotulo_campo"))
        self.usuario = QLineEdit()
        self.usuario.setProperty("grande", "true")
        self.usuario.setFixedHeight(DIMENSAO["altura_controle_grande"])
        self.usuario.setPlaceholderText("ex.: ana.souza")
        self.usuario.setAccessibleName("Usuário")
        vf.addWidget(self.usuario)
        vf.addSpacing(ESPACO["md"])

        vf.addWidget(rotulo("Senha", "rotulo_campo"))
        self.senha = QLineEdit()
        self.senha.setProperty("grande", "true")
        self.senha.setFixedHeight(DIMENSAO["altura_controle_grande"])
        self.senha.setEchoMode(QLineEdit.EchoMode.Password)
        self.senha.setAccessibleName("Senha")
        self._acao_olho = self.senha.addAction(icone("eye", "texto_terciario"), QLineEdit.ActionPosition.TrailingPosition)
        self._acao_olho.setToolTip("Mostrar senha")
        self._acao_olho.triggered.connect(self._alternar_senha)
        vf.addWidget(self.senha)
        vf.addSpacing(ESPACO["xl"])

        self.botao = Botao("Entrar", "primaria", grande=True)
        self.botao.setFixedHeight(DIMENSAO["altura_controle_grande"])
        self.botao.setDefault(True)
        self.botao.clicked.connect(self._enviar)
        vf.addWidget(self.botao)
        # enquanto o app confere as credenciais (ocupado(True)): indicador + texto
        self.verificando = QWidget()
        lv = QHBoxLayout(self.verificando)
        lv.setContentsMargins(0, ESPACO["md"], 0, 0)
        lv.setSpacing(ESPACO["sm"])
        lv.addStretch(1)
        lv.addWidget(IndicadorCarregamento(18))
        lv.addWidget(rotulo("Verificando credenciais…", "secundario"))
        lv.addStretch(1)
        self.verificando.hide()
        vf.addWidget(self.verificando)
        self.usuario.returnPressed.connect(self.senha.setFocus)
        self.senha.returnPressed.connect(self._enviar)
        self.usuario.textChanged.connect(self._limpar_erro)
        self.senha.textChanged.connect(self._limpar_erro)
        vf.addStretch(3)
        rodape = rotulo("  ·  ".join(x for x in (m.assinatura, f"versão {versao}" if versao else "") if x), "legenda")
        vf.addWidget(rodape)
        h.addWidget(form, 1)

        externo.addWidget(cartao, 0, Qt.AlignmentFlag.AlignHCenter)
        externo.addStretch(1)
        gerenciador().tema_alterado.connect(self._atualizar_icones)

    def ocupado(self, sim: bool = True) -> None:
        """Enquanto o app confere as credenciais: campos e botão bloqueados,
        o botão diz "Entrando…" e aparece o indicador com "Verificando credenciais…"."""
        for w in (self.usuario, self.senha, self.botao):
            w.setEnabled(not sim)
        self.botao.setText("Entrando…" if sim else "Entrar")
        self.verificando.setVisible(sim)
        if not sim:
            self.senha.setFocus()

    @property
    def esta_ocupado(self) -> bool:
        return self.verificando.isVisible()

    def mostrar_erro(self, mensagem: str = "Usuário ou senha incorretos. Confira e tente de novo.") -> None:
        self.aviso.mostrar(mensagem, "erro")
        for campo in (self.usuario, self.senha):
            campo.setProperty("invalido", "true")
            repolir(campo)
        self.senha.selectAll()
        self.senha.setFocus()

    def limpar(self) -> None:
        self.usuario.clear()
        self.senha.clear()
        self._limpar_erro()
        self.usuario.setFocus()

    def _limpar_erro(self, *_):
        if self.aviso.isVisible():
            self.aviso.limpar()
            for campo in (self.usuario, self.senha):
                campo.setProperty("invalido", "false")
                repolir(campo)

    def _enviar(self):
        if self.esta_ocupado:
            return
        if not self.usuario.text().strip():
            self.mostrar_erro("Informe o usuário.")
            self.usuario.setFocus()
            return
        if not self.senha.text():
            self.mostrar_erro("Informe a senha.")
            return
        self.entrar.emit(self.usuario.text().strip(), self.senha.text())

    def _alternar_senha(self):
        visivel = self.senha.echoMode() == QLineEdit.EchoMode.Password
        self.senha.setEchoMode(QLineEdit.EchoMode.Normal if visivel else QLineEdit.EchoMode.Password)
        self._acao_olho.setToolTip("Ocultar senha" if visivel else "Mostrar senha")
        self._atualizar_icones()

    def _atualizar_icones(self, *_):
        oculto = self.senha.echoMode() == QLineEdit.EchoMode.Password
        self._acao_olho.setIcon(icone("eye" if oculto else "eye-off", "texto_terciario"))
