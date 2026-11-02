"""Criação de usuário pelo master e de equipamento pelos formulários."""

import pytest
from PySide6.QtCore import Qt

from app import servico

from .conftest import SENHA, entrar


def clicar(qtbot, botao):
    qtbot.mouseClick(botao, Qt.MouseButton.LeftButton)


def test_master_cria_usuario(master, janela, qtbot):
    shell = entrar(janela, qtbot, "admin")
    pagina = shell.ir_para("usuarios")
    assert {l["login"] for l in pagina.tabela.linhas()} == {"admin"}
    d = pagina.novo_usuario()
    # validação: senha curta e confirmação diferente
    d.nome.setText("Bruna Exemplo")
    d.login.setText("bruna exemplo")
    d.senha.setText("123")
    clicar(qtbot, d.botao_confirmar)
    assert d.isVisible() and d.login.property("invalido") == "true"
    assert d.senha.property("invalido") == "true"
    d.login.setText("bruna")
    d.senha.setText("senha-longa-1")
    d.confirma.setText("senha-longa-2")
    clicar(qtbot, d.botao_confirmar)
    assert d.isVisible() and d.confirma.property("invalido") == "true"
    d.confirma.setText("senha-longa-1")
    d.perfil.setCurrentIndex(d.perfil.findData("cadastro"))
    clicar(qtbot, d.botao_confirmar)
    assert not d.isVisible()
    linhas = {l["login"]: l for l in pagina.tabela.linhas()}
    assert linhas["bruna"]["perfil"] == "cadastro" and linhas["bruna"]["nome"] == "Bruna Exemplo"
    assert "criado" in pagina.aviso.texto.text()
    assert servico.autenticar("bruna", "senha-longa-1").perfil == "cadastro"
    # login repetido: erro no campo, sem fechar
    d = pagina.novo_usuario()
    d.nome.setText("Outra")
    d.login.setText("bruna")
    d.senha.setText(SENHA)
    d.confirma.setText(SENHA)
    clicar(qtbot, d.botao_confirmar)
    assert d.isVisible() and "Já existe" in d._erros[d.login].text()
    d.reject()


def test_master_edita_desativa_e_troca_senha(usuarios, master, janela, qtbot):
    shell = entrar(janela, qtbot, "admin")
    pagina = shell.ir_para("usuarios")
    # o master não pode ser desativado: botão desabilitado
    pagina.selecionar_login("admin")
    assert not pagina.ativar.isEnabled()
    pagina.selecionar_login("ler")
    alvo = pagina._selecionado()
    d = pagina.editar_usuario(alvo)
    d.perfil.setCurrentIndex(d.perfil.findData("cadastro"))
    clicar(qtbot, d.botao_confirmar)
    assert servico.autenticar("ler", SENHA).perfil == "cadastro"
    pagina.alternar_ativo(alvo, confirmar=False)
    assert not next(u for u in servico.listar_usuarios(master) if u.login == "ler").ativo
    d = pagina.trocar_senha(alvo)
    d.senha.setText("nova-senha-123")
    d.confirma.setText("nova-senha-123")
    clicar(qtbot, d.botao_confirmar)
    assert not d.isVisible()


def test_cadastro_cria_e_edita_equipamento(usuarios, janela, qtbot):
    shell = entrar(janela, qtbot, "cad")
    pagina = shell.ir_para("equipamentos")
    assert pagina.tabela.linhas() == []
    d = pagina.novo_equipamento()
    clicar(qtbot, d.botao_confirmar)                     # sem nome
    assert d.isVisible() and d.nome.property("invalido") == "true"
    d.tipo.setCurrentIndex(d.tipo.findData("estacao"))
    d.nome.setText("Estação telhado")
    d.local.setText("Campus, prédio 42")
    # nº de série, altitude e data de instalação não são pedidos no cadastro
    assert not hasattr(d, "serie") and not hasattr(d, "altitude") and not hasattr(d, "instalado")
    # ajudas viram dica (ao passar o mouse), não texto embaixo do campo
    assert d.nome.toolTip().startswith("Único no laboratório")
    clicar(qtbot, d.botao_confirmar)
    assert not d.isVisible()
    linha = pagina.tabela.linhas()[0]
    assert linha["nome"] == "Estação telhado" and linha["tipo"] == "Estação de teste"
    assert not linha["serie"] and linha["situacao"] == "Ativo"
    # filtro por tipo existe e tem o tipo
    assert pagina.filtro_tipo.findText("Estação de teste") >= 0
    # editar: desativa e muda o local
    d = pagina.editar_equipamento(linha["_eq"])
    assert not d.tipo.isEnabled()
    d.local.setText("Bacia experimental")
    assert not hasattr(d, "ativo")                       # desativar é pelo botão, não no formulário
    clicar(qtbot, d.botao_confirmar)
    linha = pagina.tabela.linhas()[0]
    assert linha["local"] == "Bacia experimental"
    # desativar (soft delete): sai da lista comum e da importação; os dados ficam
    pagina.tabela.tabela.selectRow(0)
    assert pagina.alternar.isEnabled() and pagina.alternar.text().strip() == "Desativar"
    assert pagina.alternar_ativo(linha["_eq"], confirmar=False).ativo is False
    assert pagina.tabela.linhas() == []
    assert servico.listar_equipamentos(janela.ctx.usuario) == []
    pagina.mostrar_desativados.setChecked(True)
    linha = pagina.tabela.linhas()[0]
    assert linha["situacao"] == "Desativado"
    pagina.tabela.tabela.selectRow(0)
    assert pagina.alternar.text().strip() == "Reativar"
    assert pagina.alternar_ativo(linha["_eq"]).ativo is True        # reativar não pede confirmação
    pagina.mostrar_desativados.setChecked(False)
    assert [l["nome"] for l in pagina.tabela.linhas()] == ["Estação telhado"]
    # nome repetido
    d = pagina.novo_equipamento()
    d.nome.setText("Estação telhado")
    clicar(qtbot, d.botao_confirmar)
    assert d.isVisible() and "Já existe" in d._erros[d.nome].text()
    d.reject()


def test_ficha_do_plugin_no_formulario(usuarios, janela, qtbot):
    """O formulário é gerado da ficha do plugin; a validação é do backend e o
    erro volta para o campo certo. Campos que vêm das leituras não são pedidos."""
    shell = entrar(janela, qtbot, "cad")
    pagina = shell.ir_para("equipamentos")
    d = pagina.novo_equipamento()
    d.tipo.setCurrentIndex(d.tipo.findData("estacao"))
    # a ficha da estação: um campo digitado (intervalo) e dois lidos dos dados
    assert set(d.ficha.widgets) == {"intervalo_s"} and d.titulo_ficha.isVisibleTo(d)
    d.nome.setText("Estação 1")
    d.latitude.setText("-95")
    d.ficha.widgets["intervalo_s"].setText("0")
    clicar(qtbot, d.botao_confirmar)
    assert d.isVisible()
    assert d.latitude.property("invalido") == "true"
    d.latitude.setText("-29,72")
    d.longitude.setText("-53,72")
    clicar(qtbot, d.botao_confirmar)
    assert d.isVisible() and d.ficha.widgets["intervalo_s"].property("invalido") == "true"   # erro do backend
    d.ficha.widgets["intervalo_s"].setText("60")
    clicar(qtbot, d.botao_confirmar)
    assert not d.isVisible()
    eq = pagina.tabela.linhas()[0]["_eq"]
    assert eq.atributos == {"intervalo_s": 60}
    assert (eq.latitude, eq.longitude) == (-29.72, -53.72)
    pag_eq = janela.ctx.abrir_equipamento(eq.id)
    cad = pag_eq.abas.ir_para("cadastro")
    assert cad.valores["Coordenadas"] == "−29,72000, −53,72000"
    assert "Intervalo de amostragem" in cad.valores and "Versão do firmware" not in cad.valores
    assert cad.valores_sensor["Versão do firmware"].startswith("aguardando")
    assert cad.valores_sensor["Nº de série registrado"].startswith("aguardando")
    assert not cad.aviso_serie.isVisible()


def test_mapa_preenche_e_acompanha_as_coordenadas(usuarios, janela, qtbot):
    from PySide6.QtCore import QPointF

    from design.componentes.mapa import para_geo, para_pixel

    # conversão da projeção vai e volta
    lat, lon = para_geo(*para_pixel(-29.7206, -53.7163, 13), 13)
    assert abs(lat + 29.7206) < 1e-9 and abs(lon + 53.7163) < 1e-9
    shell = entrar(janela, qtbot, "cad")
    d = shell.ir_para("equipamentos").novo_equipamento()
    mapa = d.mapa
    assert mapa.marcador is None and mapa.sem_conexao            # testes sem rede: aviso no mapa
    # clique (sem arrastar) no centro marca a posição e preenche os campos
    centro = QPointF(mapa.width() / 2, mapa.height() / 2).toPoint()
    qtbot.mouseClick(mapa, Qt.MouseButton.LeftButton, pos=centro)
    lat_c, lon_c = mapa.centro()
    assert float(d.latitude.text().replace(",", ".")) == pytest.approx(lat_c, abs=1e-4)
    assert float(d.longitude.text().replace(",", ".")) == pytest.approx(lon_c, abs=1e-4)
    # digitar move o marcador
    d.latitude.setText("-28,8742")
    d.longitude.setText("-52,0705")
    d.longitude.editingFinished.emit()
    assert mapa.marcador == pytest.approx((-28.8742, -52.0705))
    # zoom pelos botões, com limites
    z = mapa.zoom
    mapa.mudar_zoom(+1)
    assert mapa.zoom == z + 1
    for _ in range(30):
        mapa.mudar_zoom(-1)
    assert mapa.zoom == 2
    d.nome.setText("Estação mapa")
    clicar(qtbot, d.botao_confirmar)
    assert not d.isVisible()
    eq = shell.pagina("equipamentos").tabela.linhas()[0]["_eq"]
    assert (eq.latitude, eq.longitude) == (-28.8742, -52.0705)
    # ao editar, o mapa abre no equipamento
    d = shell.pagina("equipamentos").editar_equipamento(eq)
    assert d.mapa.marcador == pytest.approx((-28.8742, -52.0705))
    d.reject()
