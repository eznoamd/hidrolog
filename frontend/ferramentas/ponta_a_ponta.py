#!/usr/bin/env python3
"""Teste ponta a ponta e gerador das capturas, com os plugins de teste do backend.

    QT_QPA_PLATFORM=offscreen venv/bin/python ferramentas/ponta_a_ponta.py [--zip ENVIO.zip]
                                                                           [--saida capturas] [--temp DIR]

O app não traz nenhum plugin de sensor: aqui o sensor é a "Estação de teste"
(backend/tests/sensor_estacao) e o plugin instalado pelo gerenciador é o
termômetro de exemplo (exemplos/plugin-termometro). Sem --zip, o envio é
um .zip feito de backend/tests/dados.

Num banco novo (HIDROLOG_DADOS_DIR num diretório temporário):
 1. abre o app e mostra a tela "falta criar o master";
 2. cria o master pelo comando de linha do backend (python -m app criar-master);
 3. faz login, cadastra um usuário de cada perfil e dois equipamentos pela tela;
 4. importa o .zip pela tela de importação (thread + progresso) e confere o resumo;
 5. navega por todas as páginas (inclusive a página do equipamento, com as abas do plugin e as
    comuns) e grava capturas 1440 × 900 nos temas claro e escuro;
 6. no tema escuro reimporta o mesmo .zip (deduplicação: 0 novas) e exporta CSV;
 7. gerenciador de plugins: importa o termômetro de exemplo (pasta) com confirmação e senha, reinicia,
    usa o equipamento dele, desativa o plugin e reinicia (equipamento sem plugin).
Sai com código 1 se alguma conferência falhar.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1]
RAIZ = FRONT.parent
TESTES_BACKEND = RAIZ / "backend" / "tests"
TERMOMETRO = RAIZ / "exemplos" / "plugin-termometro"
SENHA = "senha-ponta-a-ponta"


def zip_dos_dados_de_teste(destino: Path) -> Path:
    """Um "cartão SD" com as 13 leituras do sensor de teste e um log que é ignorado."""
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        for arq in sorted((TESTES_BACKEND / "dados").rglob("*.txt")):
            z.write(arq, arq.relative_to(TESTES_BACKEND / "dados").as_posix())
        z.writestr("estacao_erros.log", "20261011051200 sem a chuva\n")
    return destino


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--zip", default=None, help="envio a importar (padrão: os dados de teste do backend)")
    ap.add_argument("--saida", default=str(FRONT / "capturas"))
    ap.add_argument("--temp", default=None, help="pasta para o banco temporário")
    args = ap.parse_args()

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    dados_dir = Path(tempfile.mkdtemp(prefix="hidrolog-e2e-", dir=args.temp))
    os.environ["HIDROLOG_DADOS_DIR"] = str(dados_dir)
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    print(f"banco temporário: {dados_dir}")
    if args.zip is None:
        args.zip = str(zip_dos_dados_de_teste(dados_dir / "envio-teste.zip"))

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication, QFileDialog

    from app import servico
    from app.nucleo import plugins
    from design.tema import aplicar_tema, cor, modo_atual

    sys.path.insert(0, str(TESTES_BACKEND / "sensor_estacao"))
    from sensor_teste import PLUGIN as PLUGIN_ESTACAO
    plugins.registrar(PLUGIN_ESTACAO)

    from hidrolog.aplicacao import JanelaHidrolog
    from hidrolog.nucleo import configuracao, tarefas

    configuracao.configurar_log()
    app = QApplication(sys.argv[:1])
    aplicar_tema(app, "claro")
    servico.iniciar()
    falhas: list[str] = []

    def conferir(cond, texto):
        print(("  ok   " if cond else "  FALHA ") + texto)
        if not cond:
            falhas.append(texto)

    def esperar(cond, timeout=600.0, passo=0.02):
        fim = time.monotonic() + timeout
        while time.monotonic() < fim:
            app.processEvents()
            if cond():
                return True
            time.sleep(passo)
        return False

    def pausa(ms=250):
        esperar(lambda: False, ms / 1000)

    janela = JanelaHidrolog(confirmar_saida=False)
    janela.resize(1440, 900)
    janela.show()

    def capturar(nome, pm=None):
        pausa(300)
        destino = saida / f"{nome}_{modo_atual()}.png"
        (pm or janela.grab()).save(str(destino))
        print(f"  captura {destino.relative_to(FRONT) if destino.is_relative_to(FRONT) else destino}")

    def com_dialogo(dialogo):
        pausa(300)
        fundo = janela.grab()
        dialogo.adjustSize()
        pausa(150)
        pm_d = dialogo.grab()
        final = QPixmap(fundo.size())
        final.setDevicePixelRatio(fundo.devicePixelRatio())
        p = QPainter(final)
        p.drawPixmap(0, 0, fundo)
        veu = QColor(cor("texto"))
        veu.setAlphaF(0.35 if modo_atual() == "claro" else 0.15)
        p.fillRect(final.rect(), veu)
        w = fundo.width() / fundo.devicePixelRatio()
        h = fundo.height() / fundo.devicePixelRatio()
        dw = pm_d.width() / pm_d.devicePixelRatio()
        dh = pm_d.height() / pm_d.devicePixelRatio()
        x, y = int((w - dw) / 2), int((h - dh) / 2.4)
        p.drawPixmap(x, y, pm_d)
        p.setPen(QColor(cor("borda_forte")))
        p.drawRect(x - 1, y - 1, int(dw) + 1, int(dh) + 1)
        p.end()
        return final

    def alternar_tema():
        janela.shell.lateral.botao_tema.click()
        pausa(400)

    # ------------------------------------------------------------------ 1. sem master
    print("1. primeira execução, sem master")
    conferir(janela.pilha.currentWidget() is janela.sem_master, "tela 'falta criar o master'")
    capturar("01_sem_master")
    aplicar_tema(app, "escuro")
    capturar("01_sem_master")
    aplicar_tema(app, "claro")

    # ------------------------------------------------------------------ 2. master pelo comando de linha
    print("2. master pelo comando de linha do backend")
    backend = RAIZ / "backend"
    python_backend = backend / "venv" / "bin" / "python"
    r = subprocess.run([str(python_backend if python_backend.exists() else sys.executable), "-m", "app",
                        "criar-master", "--login", "admin", "--nome", "Administradora do Lab"],
                       cwd=backend, env={**os.environ, "HIDROLOG_SENHA": SENHA}, capture_output=True, text=True)
    conferir(r.returncode == 0, f"criar-master: {r.stdout.strip() or r.stderr.strip()}")
    janela.sem_master.continuar.click()
    conferir(janela.pilha.currentWidget() is janela.login, "depois do comando, vai para o login")

    # ------------------------------------------------------------------ 3. login
    print("3. login")
    capturar("02_login")
    janela.login.usuario.setText("admin")
    janela.login.senha.setText("senha-errada")
    janela.login.botao.click()
    esperar(lambda: not janela.login.esta_ocupado, 30)    # login em segundo plano
    conferir(janela.login.aviso.isVisible(), "senha errada mostra o erro")
    capturar("03_login_erro")
    aplicar_tema(app, "escuro")
    capturar("03_login_erro")
    janela.login.limpar()
    capturar("02_login")
    aplicar_tema(app, "claro")
    janela.login.usuario.setText("admin")
    janela.login.senha.setText(SENHA)
    janela.login.botao.click()
    esperar(lambda: not janela.login.esta_ocupado, 30)    # login em segundo plano
    shell = janela.shell
    conferir(shell is not None and shell.perfil == "master", "login do master")

    # usuários pela tela
    usuarios = shell.ir_para("usuarios")
    for login, nome, perfil in (("ana.souza", "Ana Souza", "cadastro"), ("caio.lemos", "Caio Lemos", "leitura"),
                                ("rita.prado", "Rita Prado", "leitura")):
        d = usuarios.novo_usuario()
        d.nome.setText(nome)
        d.login.setText(login)
        d.perfil.setCurrentIndex(d.perfil.findData(perfil))
        d.senha.setText(SENHA)
        d.confirma.setText(SENHA)
        d.botao_confirmar.click()
    conferir(len(usuarios.tabela.linhas()) == 4, "3 usuários criados pela tela")
    rita = next(l["_usuario"] for l in usuarios.tabela.linhas() if l["login"] == "rita.prado")
    usuarios.alternar_ativo(rita, confirmar=False)

    # equipamento pela tela
    eqs = shell.ir_para("equipamentos")
    d = eqs.novo_equipamento()
    d.tipo.setCurrentIndex(d.tipo.findData("estacao"))
    d.nome.setText("Estação 1")
    d.local.setText("Bacia experimental – Estação 1")
    d.latitude.setText("-28,8742")
    d.longitude.setText("-52,0705")
    d.botao_confirmar.click()
    d = eqs.novo_equipamento()
    d.tipo.setCurrentIndex(d.tipo.findData("estacao"))
    d.nome.setText("Estação 2")
    d.local.setText("Campus – estação meteorológica")
    d.botao_confirmar.click()
    conferir(len(eqs.tabela.linhas()) == 2, "equipamentos cadastrados pela tela")

    # ------------------------------------------------------------------ 4. importação
    print(f"4. importando {Path(args.zip).name} pela tela")
    imp = shell.ir_para("importacao")
    imp.equipamento.setCurrentIndex(imp.equipamento.findData(eqs.tabela.linhas()[0]["_eq"].id
                                                             if eqs.tabela.linhas()[0]["nome"] == "Estação 1"
                                                             else eqs.tabela.linhas()[1]["_eq"].id))
    conferir(imp.area.definir_caminho(args.zip), "zip aceito pela área de soltar")
    t0 = time.monotonic()
    imp.importar.click()
    esperar(lambda: imp.painel.barra.maximum() > 0 and imp.painel.barra.value() > 0.4 * imp.painel.barra.maximum(),
            timeout=300, passo=0.005)
    capturar("06_importacao_andamento")
    esperar(lambda: tarefas.ativas() == 0, timeout=600)
    esperar(lambda: imp.painel.resumo.isVisible(), timeout=10)
    dur = time.monotonic() - t0
    r1 = imp.ultimo_resumo
    conferir(r1 is not None and r1.novas > 0, f"importação: {r1 and r1.novas} novas, {r1 and r1.duplicadas} "
             f"duplicadas, {r1 and r1.corrompidas} corrompidas, {r1 and r1.ignorados} ignorados em {dur:.1f} s")
    capturar("07_importacao_resumo")

    def telas_gerais():
        for nome, chave, preparar in (
            ("04_inicio", "inicio", None),
            ("05_equipamentos", "equipamentos", None),
            ("08_historico", "historico", None),
            ("09_exportacao", "exportacao", None),
            ("16_usuarios", "usuarios", lambda w: w.selecionar_login("ana.souza")),
        ):
            w = shell.ir_para(chave)
            if preparar:
                preparar(w)
            capturar(nome)

    eq1_id = next(l["_eq"].id for l in eqs.tabela.linhas() if l["nome"] == "Estação 1")

    def telas_equipamento():
        pagina = janela.ctx.abrir_equipamento(eq1_id)
        aba = pagina.abas.ir_para("leituras")
        esperar(lambda: tarefas.ativas() == 0, 60)
        conferir(len(aba.leituras) == r1.validas, f"aba do plugin: {len(aba.leituras)} leituras válidas")
        capturar("10_equipamento_leituras")
        for nome, chave in (("24_equipamento_envios", "envios"), ("25_equipamento_cadastro", "cadastro"),
                            ("26_equipamento_qualidade", "qualidade")):
            pagina.abas.ir_para(chave)
            esperar(lambda: tarefas.ativas() == 0, 60)
            capturar(nome)
        q = pagina.abas.widget("qualidade")
        codigos = sorted(l["regra"] for l in q.tabela.linhas())
        conferir({"sem_dados", "leituras_faltando"} <= set(codigos), f"ocorrências de qualidade: {codigos}")
        d = q.abrir_regra(next(l["_regra"] for l in q.regras.linhas() if l["_regra"].codigo == "chuva_impossivel"))
        capturar("30_ajustar_regra", com_dialogo(d))
        d.reject()
        d = pagina.abas.widget("cadastro").abrir_edicao()
        capturar("29_formulario_ficha", com_dialogo(d))
        d.reject()
        pagina.abas.ir_para("leituras")

    def formulario_com_erro():
        usu = shell.ir_para("usuarios")
        d = usu.novo_usuario()
        d.nome.setText("Gabriel Teixeira")
        d.login.setText("gabriel t")
        d.senha.setText("1234567")
        d.botao_confirmar.click()
        conferir(d.isVisible() and d.login.property("invalido") == "true", "formulário recusa login com espaço")
        capturar("18_formulario_erro", com_dialogo(d))
        d.reject()

    print("5. páginas, tema claro")
    telas_gerais()
    telas_equipamento()
    hist = shell.ir_para("historico")
    d = hist.abrir_detalhe(hist.tabela.linhas()[0])
    capturar("17_detalhe_envio", com_dialogo(d))
    d.accept()
    formulario_com_erro()

    print("6. tema escuro: reimportação (deduplicação) e exportação")
    alternar_tema()
    conferir(configuracao.tema_salvo() == "escuro", "tema escuro salvo nas preferências")
    imp = shell.ir_para("importacao")
    imp.importar.click()
    esperar(lambda: imp.painel.barra.maximum() > 0 and imp.painel.barra.value() > 0.4 * imp.painel.barra.maximum(),
            timeout=300, passo=0.005)
    capturar("06_importacao_andamento")
    esperar(lambda: tarefas.ativas() == 0, timeout=600)
    esperar(lambda: imp.painel.resumo.isVisible(), timeout=10)
    r2 = imp.ultimo_resumo
    conferir(r2 is not r1 and r2.novas == 0 and r2.duplicadas == r1.novas + r1.duplicadas,
             f"reimportação: {r2.novas} novas, {r2.duplicadas} duplicadas")
    capturar("07_importacao_resumo")
    exp = shell.ir_para("exportacao")
    destino = dados_dir / "exportado.csv"
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(destino), ""))
    exp.formato.setCurrentIndex(exp.formato.findText("CSV", Qt.MatchFlag.MatchStartsWith))
    exp.exportar.click()
    esperar(lambda: tarefas.ativas() == 0 and exp.resultado.isVisible(), 120)
    conferir(destino.exists() and exp.ultimo.leituras == r1.validas,
             f"exportação CSV: {exp.ultimo and exp.ultimo.leituras} leituras, {destino.stat().st_size if destino.exists() else 0} bytes")
    telas_gerais()
    telas_equipamento()
    hist = shell.ir_para("historico")
    d = hist.abrir_detalhe(hist.tabela.linhas()[0])
    capturar("17_detalhe_envio", com_dialogo(d))
    d.accept()
    formulario_com_erro()
    usu = shell.ir_para("usuarios")
    usu.selecionar_login("ana.souza")
    from design.componentes import DialogoConfirmacao
    d = DialogoConfirmacao("Desativar Ana Souza?", "ana.souza não conseguirá mais entrar. Os envios feitos por esta "
                           "pessoa continuam no histórico. Você pode reativar o usuário depois.",
                           "Desativar usuário", destrutivo=True, parent=janela)
    capturar("19_confirmacao", com_dialogo(d))
    d.reject()
    alternar_tema()
    d = DialogoConfirmacao("Desativar Ana Souza?", "ana.souza não conseguirá mais entrar. Os envios feitos por esta "
                           "pessoa continuam no histórico. Você pode reativar o usuário depois.",
                           "Desativar usuário", destrutivo=True, parent=janela)
    capturar("19_confirmacao", com_dialogo(d))
    d.reject()

    print("7. perfil leitura")
    for modo in ("claro", "escuro"):
        aplicar_tema(app, modo)
        janela.encerrar_sessao()
        janela.login.usuario.setText("caio.lemos")
        janela.login.senha.setText(SENHA)
        janela.login.botao.click()
        esperar(lambda: not janela.login.esta_ocupado, 30)    # login em segundo plano
        shell = janela.shell
        vis = {c for c, p in shell._paginas.items() if not p.botao.isHidden()}
        conferir("importacao" not in vis and "usuarios" not in vis, f"leitura ({modo}) sem Importar nem Usuários")
        shell.ir_para("equipamentos")
        capturar("20_perfil_leitura")
        pagina = janela.ctx.abrir_equipamento(eq1_id)
        esperar(lambda: tarefas.ativas() == 0, 60)
        conferir("importar" not in pagina.abas.chaves(), f"leitura ({modo}) sem a aba Importar")
        capturar("15_equipamento_leitura")

    print("8. gerenciador de plugins")
    from hidrolog.nucleo import registro


    def entrar_master():
        janela.encerrar_sessao()
        janela.login.usuario.setText("admin")
        janela.login.senha.setText(SENHA)
        janela.login.botao.click()
        esperar(lambda: not janela.login.esta_ocupado, 30)    # login em segundo plano
        return janela.shell

    def reiniciar():
        """Como fechar e abrir o Hidrolog: recarrega os plugins e migra o banco."""
        janela.encerrar_sessao()
        tarefas.esperar_todas()
        servico.encerrar()
        servico.iniciar()
        registro.esquecer()
        return entrar_master()

    aplicar_tema(app, "claro")
    shell = entrar_master()
    conf = shell.ir_para("configuracoes")
    conf.plugins.escolher_local = lambda: str(TERMOMETRO)
    conf.plugins.importar_de("computador")
    esperar(lambda: tarefas.ativas() == 0 and conf.plugins.dialogo is not None, 60)
    d = conf.plugins.dialogo
    capturar("22_instalar_plugin", com_dialogo(d))
    aplicar_tema(app, "escuro")
    capturar("22_instalar_plugin", com_dialogo(d))
    aplicar_tema(app, "claro")
    d.senha.setText("senha-errada")
    d.confirmar.click()
    conferir(d.isVisible() and "Restam 2" in d.erro.text(), f"senha errada recusada: {d.erro.text()}")
    capturar("22_instalar_plugin_senha_errada", com_dialogo(d))
    d.senha.setText(SENHA)
    d.confirmar.click()
    conferir(not d.isVisible() and "Reinicie" in conf.aviso.texto.text(), "termômetro de exemplo instalado (pasta)")
    capturar("21_configuracoes_plugins")
    conf.abas.ir_para("auditoria")
    capturar("23_auditoria_plugins")
    shell = reiniciar()
    conf = shell.ir_para("configuracoes")
    estados = {l["codigo"]: l["estado"] for l in conf.plugins.tabela.linhas()}
    conferir(estados.get("termometro") == "ativo", f"depois de reiniciar, termometro {estados.get('termometro')}")
    master = janela.ctx.usuario
    termo = servico.criar_equipamento(master, "termometro", "Termômetro 1", local="Estação do campus")
    r = servico.importar_caminho(master, termo.id, TERMOMETRO / "hidrolog_termometro" / "amostra")
    conferir(r.novas == 144, f"amostra do termômetro: {r.novas} novas")
    pagina = janela.ctx.abrir_equipamento(termo.id)
    esperar(lambda: tarefas.ativas() == 0, 30)
    capturar("27_equipamento_termometro")
    aplicar_tema(app, "escuro")
    capturar("27_equipamento_termometro")
    shell.ir_para("configuracoes").recarregar()
    capturar("21_configuracoes_plugins")
    conf = shell.ir_para("configuracoes")
    conf.abas.ir_para("auditoria")
    capturar("23_auditoria_plugins")
    conf.abas.ir_para("plugins")
    info = next(l["_info"] for l in conf.plugins.tabela.linhas() if l["codigo"] == "termometro")
    d = conf.plugins.alternar_ativo(info)
    capturar("22_desativar_plugin", com_dialogo(d))
    aplicar_tema(app, "claro")
    capturar("22_desativar_plugin", com_dialogo(d))
    aplicar_tema(app, "escuro")
    d.senha.setText(SENHA)
    d.confirmar.click()
    shell = reiniciar()
    pagina = janela.ctx.abrir_equipamento(termo.id)
    conferir(pagina.abas.titulos()[0] == "Qualidade" and pagina.sem_plugin.isVisible(),
             "plugin desativado: só as abas comuns, com o aviso")
    pagina.abas.ir_para("envios")
    capturar("28_equipamento_sem_plugin")
    aplicar_tema(app, "claro")
    capturar("28_equipamento_sem_plugin")
    leituras = servico.resumo_leituras(janela.ctx.usuario, termo.id).leituras
    exp = pagina.abas.ir_para("exportar")
    conferir(exp.formato.count() == 1 and "genérico" in exp.formato.currentText(),
             "exportação genérica oferecida sem o plugin")
    destino = dados_dir / "generico.csv"
    servico.exportar(janela.ctx.usuario, termo.id, None, None, "generico", destino)
    linhas_csv = destino.read_text(encoding="utf-8").splitlines()
    conferir(len(linhas_csv) == 145, f"exportação genérica com o plugin desativado: {len(linhas_csv) - 1} leituras "
             "(os dados ficaram no banco)")

    tarefas.esperar_todas()
    servico.encerrar()
    erros_log = [l for l in configuracao.caminho_log().read_text(encoding="utf-8").splitlines() if " ERROR " in l]
    conferir(not erros_log, f"log sem erros ({len(erros_log)} linha(s) ERROR em {configuracao.caminho_log()})")
    print(f"\n{len(falhas)} falha(s)" if falhas else "\ntudo certo")
    return 1 if falhas else 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
