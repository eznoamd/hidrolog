"""Montagem do shell (JanelaPrincipal do design) para um usuário logado.
A barra lateral é fixa (não cresce com os sensores): Geral, Administração e
Recentes (os últimos equipamentos abertos). Cada equipamento tem a página
dele, com as abas do plugin do tipo e as abas comuns."""

from __future__ import annotations

from design.componentes import JanelaPrincipal

from . import configuracao
from .contexto import Contexto
from .telas.ajuda import PaginaAjuda
from .telas.conta import PaginaConta
from .telas.configuracoes import PaginaConfiguracoes
from .telas.equipamentos import PaginaEquipamentos
from .telas.exportacao import PaginaExportacao
from .telas.historico import PaginaHistorico
from .telas.importacao import PaginaImportacao
from .telas.inicio import PaginaInicio
from .telas.equipamento import montar_recentes
from .telas.usuarios import PaginaUsuarios

CADASTRO = {"master", "cadastro"}


def montar_shell(ctx: Contexto) -> JanelaPrincipal:
    shell = JanelaPrincipal()
    ctx.shell = shell
    shell.adicionar_pagina("inicio", "Início", lambda: PaginaInicio(ctx), "layout-dashboard", ordem=0)
    shell.adicionar_pagina("equipamentos", "Equipamentos", lambda: PaginaEquipamentos(ctx), "cpu", ordem=1)
    shell.adicionar_pagina("importacao", "Importar dados", lambda: PaginaImportacao(ctx), "upload",
                           perfis=CADASTRO, ordem=2)
    shell.adicionar_pagina("historico", "Histórico de envios", lambda: PaginaHistorico(ctx), "history", ordem=3)
    shell.adicionar_pagina("exportacao", "Exportar dados", lambda: PaginaExportacao(ctx), "download", ordem=4)
    shell.adicionar_secao("admin", "Administração", ordem=900, recolhivel=False)
    shell.adicionar_pagina("usuarios", "Usuários", lambda: PaginaUsuarios(ctx), "users", secao="admin",
                           perfis={"master"})
    shell.adicionar_pagina("configuracoes", "Configurações", lambda: PaginaConfiguracoes(ctx), "settings",
                           secao="admin", perfis={"master"}, ordem=200)
    montar_recentes(shell, ctx)
    shell.adicionar_pagina("conta", "Minha conta", lambda: PaginaConta(ctx), "user", migalha="Conta",
                           na_navegacao=False)
    shell.minha_conta_solicitada.connect(lambda: shell.ir_para("conta"))
    shell.adicionar_pagina("ajuda", "Central de ajuda", lambda: PaginaAjuda(ctx), "circle-help", migalha="Ajuda",
                           na_navegacao=False)
    shell.ajuda_solicitada.connect(lambda: shell.ir_para("ajuda"))

    def ao_mudar_pagina(chave: str) -> None:
        pagina = shell.pagina(chave)
        if hasattr(pagina, "ao_mostrar"):
            try:
                pagina.ao_mostrar()
            except Exception as erro:  # noqa: BLE001
                texto = ctx.tratar_erro(erro, f"abrir {chave}")
                if hasattr(pagina, "aviso"):
                    pagina.aviso.mostrar(texto, "erro")

    shell.pagina_alterada.connect(ao_mudar_pagina)
    shell.tema_alterado.connect(configuracao.salvar_tema)
    shell.definir_usuario(ctx.usuario.nome, ctx.usuario.perfil, ctx.usuario.login)
    shell.ir_para("inicio")   # todas as sessões começam no Início (todos os perfis o veem)
    return shell
