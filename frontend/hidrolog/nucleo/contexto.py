"""Contexto da sessão: o usuário logado, o shell e os avisos de dados alterados.

Uma instância por login. As páginas recebem o contexto e:
- conferem o perfil com `ctx.pode("cadastro")` para esconder o que não podem;
- avisam `ctx.dados_alterados.emit("envios")` depois de mudar algo, para as
  outras páginas recarregarem (tipos: "usuarios", "equipamentos", "envios");
- passam os erros por `ctx.tratar_erro(erro)`, que grava no log e devolve a
  mensagem amigável (e encerra a sessão se o usuário foi desativado).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from app import servico
from app.nucleo.erros import ErroAutenticacao
from app.nucleo.tipos import Equipamento, TipoSensor, Usuario

from . import erros

if TYPE_CHECKING:
    from design.componentes import JanelaPrincipal


class Contexto(QObject):
    dados_alterados = Signal(str)
    sessao_expirada = Signal(str)

    def __init__(self, usuario: Usuario):
        super().__init__()
        self.usuario = usuario
        self.shell: "JanelaPrincipal | None" = None
        self._nomes_tipos: dict[str, str] = {}
        self.extras: dict = {}  # estado dos plugins (ex.: cache de dados), por sessão
        self.versao_dados = 0   # muda a cada importação: as abas descartam o cache
        self.dados_alterados.connect(self._ao_alterar)

    def _ao_alterar(self, tipo: str) -> None:
        if tipo == "envios":
            self.versao_dados += 1

    # ---------------------------------------------------------------- perfil
    @property
    def perfil(self) -> str:
        return self.usuario.perfil

    def pode(self, perfil: str) -> bool:
        return self.usuario.pode(perfil)

    # ---------------------------------------------------------------- erros
    def tratar_erro(self, erro: BaseException, contexto: str = "") -> str:
        erros.registrar(erro, contexto)
        if isinstance(erro, ErroAutenticacao):
            self.sessao_expirada.emit(erros.mensagem(erro))
        return erros.mensagem(erro, self.perfil)

    # ---------------------------------------------------------------- tipos de sensor
    def definir_nome_tipo(self, codigo: str, nome: str) -> None:
        self._nomes_tipos[codigo] = nome

    def nome_tipo(self, codigo: str) -> str:
        """Nome do tipo de sensor para a tela (o do manifesto do plugin)."""
        if codigo not in self._nomes_tipos:
            self._nomes_tipos.update({t.codigo: t.nome for t in servico.listar_tipos_sensor(incluir_ausentes=True)})
        return self._nomes_tipos.get(codigo, codigo)

    def tipos_sensor(self) -> list[TipoSensor]:
        return [TipoSensor(t.codigo, self.nome_tipo(t.codigo)) for t in servico.listar_tipos_sensor()]

    # ---------------------------------------------------------------- navegação
    def ir_para(self, chave: str):
        if self.shell is not None:
            return self.shell.ir_para(chave)
        return None

    def abrir_equipamento(self, eq_id: int):
        """Abre a página do equipamento (e o põe no topo dos Recentes)."""
        from .telas.equipamento import chave_pagina, registrar_recente

        if self.shell is None:
            return None
        eq = servico.obter_equipamento(self.usuario, eq_id)
        registrar_recente(self.shell, self, eq)
        return self.shell.ir_para(chave_pagina(eq_id))

    def atualizar_recente(self, eq: Equipamento) -> None:
        """O nome do equipamento mudou: atualiza o item dos Recentes."""
        from .telas.equipamento import chave_pagina

        p = self.shell._paginas.get(chave_pagina(eq.id)) if self.shell is not None else None
        if p is not None and p.titulo != eq.nome:
            p.titulo = eq.nome
            p.botao.setText(eq.nome)
            p.botao.setAccessibleName(eq.nome)


def rotulo_equipamento(eq: Equipamento, com_tipo: bool = False, ctx: Contexto | None = None) -> str:
    """'Pluviômetro 1 · nº 450994' (com_tipo: '… · Pluviômetro de báscula')."""
    partes = [eq.nome]
    if eq.numero_serie:
        partes.append(f"nº {eq.numero_serie}")
    if com_tipo and ctx is not None:
        partes.append(ctx.nome_tipo(eq.tipo_sensor))
    texto = " · ".join(partes)
    return texto if eq.ativo else f"{texto} (desativado)"
