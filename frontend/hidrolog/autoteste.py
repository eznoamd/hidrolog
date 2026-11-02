"""Autoteste do app instalado: confere, sem abrir janela na tela, que o pacote
tem tudo de que precisa para funcionar.

    Hidrolog.exe --autoteste [relatorio.txt] [--plugin PASTA]       (no app empacotado)
    python -m hidrolog.autoteste [relatorio.txt] [--plugin PASTA]   (em desenvolvimento)

Abre um banco novo numa pasta temporária (com todas as migrações), cria um
master, aplica o tema (fontes, ícones, folha de estilo), carrega os tópicos da
ajuda e monta a janela principal. Com --plugin, também instala o plugin da
pasta pelo gerenciador, reabre o banco (como ao reiniciar o app) e importa e
exporta a amostra dele: confere que um plugin instalado depois encontra no
pacote tudo o que usa. Escreve uma linha por conferência no
relatório (ou na saída) e devolve 0 se tudo deu certo. O instalador do Windows
roda isto no CI antes de gerar o Setup.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path


def _conferir_plugin(pasta_plugin: str, conferir) -> None:
    """Instala o plugin pelo gerenciador, "reinicia" e usa a amostra dele."""
    from app import servico
    from app.nucleo import plugins

    master = servico.autenticar("autoteste", "senha-do-autoteste")
    pacote = servico.preparar_plugin(master, "pasta", pasta_plugin)
    servico.instalar_plugin(master, pacote.token, "senha-do-autoteste")
    servico.encerrar()
    servico.iniciar()                                  # como reiniciar o app: carrega e migra o plugin
    plugin = plugins.obter(pacote.codigo)
    conferir(True, f"plugin {pacote.codigo} {pacote.versao} instalado e carregado")
    eq = servico.criar_equipamento(master, pacote.codigo, "Autoteste")
    resumo = servico.importar_caminho(master, eq.id, plugin.amostra)
    conferir(resumo.novas > 0, f"amostra do plugin importada ({resumo.novas} leituras)")
    formato = servico.listar_formatos_exportacao(eq.id)[0].codigo
    saida = servico.exportar(master, eq.id, None, None, formato, Path(servico.configuracao().diretorio_dados))
    conferir(Path(saida.caminho).stat().st_size > 0, f"exportação {formato} do plugin")
    if plugin.interface:
        conferir(bool(plugin.modulo_interface().ABAS), "interface (abas) do plugin")


def executar(relatorio: str | None = None, plugin: str | None = None) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pasta = Path(tempfile.mkdtemp(prefix="hidrolog-autoteste-"))
    os.environ["HIDROLOG_DADOS_DIR"] = str(pasta)
    os.environ["HIDROLOG_MARCA_DIR"] = str(pasta / "marca")
    os.environ["HIDROLOG_PROCESSOS"] = "1"
    linhas: list[str] = []
    falhas = 0

    def conferir(condicao, texto: str) -> None:
        nonlocal falhas
        linhas.append(("ok     " if condicao else "FALHA  ") + texto)
        falhas += not condicao

    try:
        from PySide6.QtGui import QFontDatabase
        from PySide6.QtWidgets import QApplication

        from app import servico
        from app.nucleo.administracao import criar_master
        from design.tema import aplicar_tema, icone

        app = QApplication.instance() or QApplication(sys.argv[:1])
        aplicar_tema(app, "claro")
        conferir(not icone("user").isNull(), "ícones do tema")
        familias = QFontDatabase.families()
        conferir("Inter" in familias and any(f.startswith("JetBrains Mono") for f in familias), "fontes embarcadas")

        banco = servico.iniciar()
        criar_master(banco, "autoteste", "Autoteste", "senha-do-autoteste")
        usuario = servico.autenticar("autoteste", "senha-do-autoteste")
        conferir(usuario.perfil == "master", "banco novo com as migrações e um master")

        from hidrolog import ajuda
        conferir(all(ajuda.texto(t).startswith("# ") for t in ajuda.TOPICOS), f"{len(ajuda.TOPICOS)} tópicos da ajuda")

        from hidrolog.aplicacao import JanelaHidrolog
        janela = JanelaHidrolog(confirmar_saida=False)
        janela.show()
        app.processEvents()
        conferir(janela.pilha.currentWidget() is janela.login, "janela principal com a tela de login")
        janela.close()
        if plugin:
            _conferir_plugin(plugin, conferir)
        servico.encerrar()
    except Exception:  # noqa: BLE001 - o relatório leva o erro completo
        falhas += 1
        linhas.append("FALHA  " + traceback.format_exc())
    finally:
        shutil.rmtree(pasta, ignore_errors=True)

    linhas.append("tudo certo" if not falhas else f"{falhas} falha(s)")
    texto = "\n".join(linhas) + "\n"
    if relatorio:
        Path(relatorio).write_text(texto, encoding="utf-8")
    else:
        print(texto, end="")
    return 0 if not falhas else 1


def principal(argumentos: list[str]) -> int:
    """`[relatorio] [--plugin PASTA]`, para o Hidrolog.exe e o python -m."""
    plugin = None
    if "--plugin" in argumentos:
        i = argumentos.index("--plugin")
        plugin = argumentos[i + 1]
        argumentos = argumentos[:i] + argumentos[i + 2:]
    return executar(argumentos[0] if argumentos else None, plugin)


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
