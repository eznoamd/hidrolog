"""Gerenciador de plugins (F2): importar de pasta, .zip e GitHub (sem rede),
senha do master conferida de novo (3 tentativas), auditoria, plugin
incompativel recusado, desativar sem apagar dados, atualizar e voltar versao,
backup do banco antes de migrar plugin."""

import http.server
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

import pytest

from app import servico
from app.nucleo import gerenciador, plugins
from app.nucleo.administracao import criar_master
from app.nucleo.erros import ErroPermissao, ErroServico

from .conftest import SENHA, config_teste

RAIZ = Path(__file__).resolve().parents[2]
TESTES = Path(__file__).resolve().parent
TERMOMETRO = RAIZ / "exemplos" / "plugin-termometro"     # o plugin de exemplo do repositorio
SENSOR_TESTE = TESTES / "sensor_estacao"
BACKEND = RAIZ / "backend"


@pytest.fixture(scope="module")
def site_com_entry_point(tmp_path_factory):
    """Um "pacote instalado" que declara o sensor de teste no grupo de entry
    points hidrolog.plugins: no processo do _reabrir ele e um plugin interno."""
    site = tmp_path_factory.mktemp("site")
    info = site / "hidrolog_sensor_teste-1.0.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text("Metadata-Version: 2.1\nName: hidrolog-sensor-teste\nVersion: 1.0.0\n")
    (info / "entry_points.txt").write_text("[hidrolog.plugins]\nestacao = sensor_teste:PLUGIN\n")
    return site


@pytest.fixture
def app_dados(tmp_path):
    """Banco + pasta de plugins do app num diretorio temporario (como o app real)."""
    pasta = tmp_path / "dados"
    pasta.mkdir()
    url = f"sqlite:///{pasta / 'hidrolog.db'}"
    b = servico.iniciar(config=config_teste(url, diretorio_dados=pasta))
    criar_master(b, "admin", "Administrador", SENHA)
    yield pasta, servico.autenticar("admin", SENHA)
    servico.encerrar()
    plugins.redefinir()


def _copia_termometro(destino: Path, **mudancas) -> Path:
    shutil.copytree(TERMOMETRO, destino, ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    toml = destino / "hidrolog-plugin.toml"
    texto = toml.read_text()
    for chave, valor in mudancas.items():
        linhas = [l for l in texto.splitlines() if not l.startswith(f"{chave} =")]
        linhas.append(f"{chave} = {json.dumps(valor)}")
        texto = "\n".join(linhas) + "\n"
    toml.write_text(texto)
    return destino


def _zip_de(pasta: Path, prefixo: str = "") -> bytes:
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        for arq in sorted(pasta.rglob("*")):
            if arq.is_file() and "__pycache__" not in arq.parts:
                z.write(arq, prefixo + arq.relative_to(pasta).as_posix())
    return saida.getvalue()


def _auditoria(master):
    return [(a.acao, a.resultado) for a in reversed(servico.listar_auditoria_plugins(master))]


def _reabrir(pasta: Path, codigo: str = "termometro", site: Path | None = None) -> dict:
    """Abre o app num processo novo (como reiniciar o Hidrolog) e conta o que carregou."""
    script = (
        "import json, sqlite3, sys\n"
        "from app import servico\nfrom app.nucleo import plugins\n"
        "servico.iniciar()\n"
        "s = {x.codigo: x for x in plugins.situacoes() if x.estado != 'conflito'}\n"
        "con = sqlite3.connect(sys.argv[1])\n"
        "tabelas = [t for (t,) in con.execute(\"select name from sqlite_master where type='table'\")]\n"
        "n = con.execute('select count(*) from termometro_leitura').fetchone()[0] if 'termometro_leitura' in tabelas else None\n"
        "print(json.dumps({'estado': s[sys.argv[2]].estado if sys.argv[2] in s else None,\n"
        "  'versao': s[sys.argv[2]].versao if sys.argv[2] in s else None, 'leituras': n,\n"
        "  'backups': [str(p) for p in servico.banco().backups]}))\n"
        "servico.encerrar()\n")
    env = dict(os.environ, HIDROLOG_DADOS_DIR=str(pasta), HIDROLOG_PROCESSOS="1")
    if site is not None:
        env["PYTHONPATH"] = os.pathsep.join([str(site), str(SENSOR_TESTE), env.get("PYTHONPATH", "")])
    r = subprocess.run([sys.executable, "-c", script, str(pasta / "hidrolog.db"), codigo], cwd=BACKEND, env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------------ as tres origens

def test_instalar_da_pasta_com_senha(app_dados):
    pasta, master = app_dados
    pacote = servico.preparar_plugin(master, "pasta", TERMOMETRO)
    assert (pacote.codigo, pacote.versao, pacote.contrato, pacote.atualizacao) == ("termometro", "0.1.0", "1.x", False)
    assert len(pacote.sha256) == 64 and pacote.tabelas == ["termometro_leitura"]
    assert "Altura do sensor" in pacote.cadastro
    with pytest.raises(gerenciador.SenhaIncorreta) as erro:
        servico.instalar_plugin(master, pacote.token, "senha-errada")
    assert erro.value.restantes == 2
    texto = servico.instalar_plugin(master, pacote.token, SENHA)
    assert "Reinicie" in texto
    assert (pasta / "plugins" / "termometro" / "0.1.0" / "hidrolog_termometro" / "__init__.py").is_file()
    estado = json.loads((pasta / "plugins" / "plugins.json").read_text())
    assert estado["plugins"]["termometro"] == {"versao": "0.1.0", "ativo": True, "origem": "pasta", "url": "",
                                            "tag": "", "sha256": pacote.sha256}
    info = {p.codigo: p for p in servico.listar_plugins(master)}["termometro"]
    assert info.estado == "instalado" and "Reinicie" in info.pendente.capitalize()
    assert _auditoria(master) == [("importar", "recusado"), ("importar", "ok")]
    # reiniciar: o plugin carrega, as migracoes dele rodam, com backup do banco antes
    reaberto = _reabrir(pasta)
    assert reaberto["estado"] == "ativo" and reaberto["leituras"] == 0
    assert len(reaberto["backups"]) == 1 and Path(reaberto["backups"][0]).exists()
    assert "antes-migrar-termometro_0001" in reaberto["backups"][0]


def test_instalar_de_zip(app_dados, tmp_path):
    _pasta, master = app_dados
    arquivo = tmp_path / "plugin-termometro.zip"
    arquivo.write_bytes(_zip_de(TERMOMETRO, "plugin-termometro/"))
    pacote = servico.preparar_plugin(master, "zip", arquivo)
    assert pacote.sha256 == __import__("hashlib").sha256(arquivo.read_bytes()).hexdigest()
    servico.instalar_plugin(master, pacote.token, SENHA)
    assert {p.codigo: p.origem for p in servico.listar_plugins(master)}["termometro"] == "zip"


def test_instalar_do_github_com_downloader_injetado(app_dados):
    _pasta, master = app_dados
    pedidos = []

    def baixar(url):
        pedidos.append(url)
        return _zip_de(TERMOMETRO, "plugin-termometro-0.1.0/")

    pacote = servico.preparar_plugin(master, "github", url="https://github.com/laboratorio/plugin-termometro.git",
                                     tag="v0.1.0", baixar=baixar)
    assert pedidos == ["https://github.com/laboratorio/plugin-termometro/archive/refs/tags/v0.1.0.zip"]
    assert (pacote.url, pacote.tag) == ("https://github.com/laboratorio/plugin-termometro", "v0.1.0")
    servico.instalar_plugin(master, pacote.token, SENHA)
    info = {p.codigo: p for p in servico.listar_plugins(master)}["termometro"]
    assert (info.origem, info.url, info.tag) == ("github", "https://github.com/laboratorio/plugin-termometro", "v0.1.0")


def test_github_por_um_servidor_local(app_dados):
    """O download de verdade (urllib), contra um servidor HTTP local no lugar do github.com."""
    _pasta, master = app_dados
    conteudo = _zip_de(TERMOMETRO, "plugin-termometro-v0.1.0/")
    caminhos = []

    class Manipulador(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            caminhos.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.end_headers()
            self.wfile.write(conteudo)

        def log_message(self, *_):
            pass

    servidor = http.server.HTTPServer(("127.0.0.1", 0), Manipulador)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        pacote = servico.preparar_plugin(master, "github", url="https://github.com/laboratorio/plugin-termometro",
                                         tag="v0.1.0", base_github=f"http://127.0.0.1:{servidor.server_port}")
    finally:
        servidor.shutdown()
    assert caminhos == ["/laboratorio/plugin-termometro/archive/refs/tags/v0.1.0.zip"]
    assert pacote.codigo == "termometro"
    servico.cancelar_plugin(master, pacote.token)


def test_lista_confiavel_do_github(app_dados):
    _pasta, master = app_dados
    assert servico.github_confiaveis(master) == []            # desligada por padrao
    servico.definir_github_confiaveis(master, ["laboratorio"], SENHA)
    assert servico.github_confiaveis(master) == ["https://github.com/laboratorio"]
    with pytest.raises(ErroServico, match="lista de repositorios confiaveis"):
        servico.preparar_plugin(master, "github", url="https://github.com/outro/repo", tag="v1",
                                baixar=lambda url: b"")
    pacote = servico.preparar_plugin(master, "github", url="https://github.com/laboratorio/plugin-termometro", tag="v0.1.0",
                                     baixar=lambda url: _zip_de(TERMOMETRO))
    servico.cancelar_plugin(master, pacote.token)


# ------------------------------------------------------------------ senha e permissao

def test_tres_senhas_erradas_cancelam(app_dados):
    pasta, master = app_dados
    pacote = servico.preparar_plugin(master, "pasta", TERMOMETRO)
    for _ in range(2):
        with pytest.raises(gerenciador.SenhaIncorreta):
            servico.instalar_plugin(master, pacote.token, "errada")
    with pytest.raises(gerenciador.OperacaoCancelada):
        servico.instalar_plugin(master, pacote.token, "errada")
    with pytest.raises(ErroServico, match="expirou"):
        servico.instalar_plugin(master, pacote.token, SENHA)        # preparacao descartada
    assert not (pasta / "plugins" / "termometro").exists()
    assert _auditoria(master) == [("importar", "recusado"), ("importar", "recusado"), ("importar", "cancelado")]


def test_so_o_master(app_dados):
    _pasta, master = app_dados
    servico.criar_usuario(master, "cad", "Cadastro", SENHA, "cadastro")
    cadastro = servico.autenticar("cad", SENHA)
    for chamada in (lambda: servico.preparar_plugin(cadastro, "pasta", TERMOMETRO),
                    lambda: servico.listar_plugins(cadastro),
                    lambda: servico.desativar_plugin(cadastro, "estacao", SENHA)):
        with pytest.raises(ErroPermissao):
            chamada()


# ------------------------------------------------------------------ validacao

def test_contrato_incompativel_recusado(app_dados, tmp_path):
    _pasta, master = app_dados
    pacote = _copia_termometro(tmp_path / "p", contrato="2.x")
    with pytest.raises(ErroServico, match="contrato 2.x"):
        servico.preparar_plugin(master, "pasta", pacote)
    assert _auditoria(master) == [("importar", "recusado")]


@pytest.mark.parametrize("mudancas,mensagem", [
    ({"codigo": "estacao"}, "ja pertence a outro plugin"),
    ({"requer": ["modulo_que_nao_existe_xyz"]}, "dependencias"),
    ({"modulo": "nao_existe"}, "nao tem o modulo"),
])
def test_validacoes(app_dados, tmp_path, mudancas, mensagem):
    _pasta, master = app_dados
    with pytest.raises(ErroServico, match=mensagem):
        servico.preparar_plugin(master, "pasta", _copia_termometro(tmp_path / "p", **mudancas))


def test_zip_com_caminho_perigoso_e_sem_manifesto(app_dados, tmp_path):
    _pasta, master = app_dados
    ruim = tmp_path / "ruim.zip"
    with zipfile.ZipFile(ruim, "w") as z:
        z.writestr("../../fora.py", "x")
    with pytest.raises(ErroServico, match="nao permitido"):
        servico.preparar_plugin(master, "zip", ruim)
    sem = tmp_path / "sem.zip"
    with zipfile.ZipFile(sem, "w") as z:
        z.writestr("leia-me.txt", "x")
    with pytest.raises(ErroServico, match="manifesto"):
        servico.preparar_plugin(master, "zip", sem)


# ------------------------------------------------------------------ desativar, atualizar, voltar versao

def _instalar(master, origem_pasta: Path) -> None:
    pacote = servico.preparar_plugin(master, "pasta", origem_pasta)
    servico.instalar_plugin(master, pacote.token, SENHA)


def test_desativar_nao_apaga_dados(app_dados, tmp_path):
    pasta, master = app_dados
    _instalar(master, TERMOMETRO)
    assert _reabrir(pasta)["estado"] == "ativo"
    con = sqlite3.connect(pasta / "hidrolog.db")
    con.execute("insert into equipamento (tipo_sensor, nome, ativo, criado_em) values "
                "('termometro', 'Termo 1', 1, '2026-10-30 10:00:00')")
    con.execute("insert into envio (equipamento_id, usuario_id, recebido_em, canal, tipo, origem, arquivos_recebidos, "
                "ignorados, leituras, validas, corrompidas, novas, duplicadas, duracao_s) values "
                "(1, 1, '2026-10-30 10:00:00', 'local', 'pasta', 'x', 1, 0, 1, 1, 0, 1, 0, 0)")
    con.execute("insert into termometro_leitura (equipamento_id, envio_id, tempo, temperatura) values "
                "(1, 1, '2026-10-30 10:00:00', 21.5)")
    con.commit()
    con.close()
    servico.desativar_plugin(master, "termometro", SENHA)
    reaberto = _reabrir(pasta)
    assert reaberto["estado"] == "desativado" and reaberto["leituras"] == 1      # dados ficam
    servico.reativar_plugin(master, "termometro", SENHA)
    assert _reabrir(pasta)["estado"] == "ativo"
    acoes = [a for a in _auditoria(master) if a[0] in ("desativar", "reativar")]
    assert acoes == [("desativar", "ok"), ("reativar", "ok")]


def test_desativar_plugin_interno(app_dados, site_com_entry_point):
    pasta, master = app_dados
    assert _reabrir(pasta, "estacao", site_com_entry_point)["estado"] == "ativo"
    servico.desativar_plugin(master, "estacao", SENHA)
    assert _reabrir(pasta, "estacao", site_com_entry_point)["estado"] == "desativado"
    info = {p.codigo: p for p in servico.listar_plugins(master)}["estacao"]
    assert info.pendente == "sera desativado ao reiniciar"
    servico.reativar_plugin(master, "estacao", SENHA)
    assert _reabrir(pasta, "estacao", site_com_entry_point)["estado"] == "ativo"


def test_atualizar_e_voltar_versao(app_dados, tmp_path):
    pasta, master = app_dados
    _instalar(master, TERMOMETRO)
    _reabrir(pasta)
    v2 = _copia_termometro(tmp_path / "v2", versao="0.2.0")
    pacote = servico.preparar_plugin(master, "pasta", v2)
    assert pacote.atualizacao and pacote.versao_atual == "0.1.0"
    servico.instalar_plugin(master, pacote.token, SENHA)
    assert _reabrir(pasta)["versao"] == "0.2.0"
    assert gerenciador.versoes_guardadas("termometro") == ["0.1.0", "0.2.0"]
    # mesma versao de novo: recusada
    with pytest.raises(ErroServico, match="ja esta instalada"):
        servico.preparar_plugin(master, "pasta", v2)
    # sem migracao nova: pode voltar
    servico.voltar_versao_plugin(master, "termometro", "0.1.0", SENHA)
    assert _reabrir(pasta)["versao"] == "0.1.0"
    # 0.3.0 traz uma migracao nova, aplicada ao reabrir; voltar para 0.1.0 e recusado
    v3 = _copia_termometro(tmp_path / "v3", versao="0.3.0")
    (v3 / "hidrolog_termometro" / "migracoes" / "termometro_0002.py").write_text(
        'import sqlalchemy as sa\nfrom alembic import op\n\nrevision = "termometro_0002"\n'
        'down_revision = "termometro_0001"\nbranch_labels = None\ndepends_on = None\n\n\n'
        'def upgrade():\n    op.add_column("termometro_leitura", sa.Column("umidade", sa.Float(), nullable=True))\n\n\n'
        'def downgrade():\n    with op.batch_alter_table("termometro_leitura") as t:\n        t.drop_column("umidade")\n')
    pacote = servico.preparar_plugin(master, "pasta", v3)
    servico.instalar_plugin(master, pacote.token, SENHA)
    reaberto = _reabrir(pasta)
    assert reaberto["versao"] == "0.3.0" and any("termometro_0002" in b for b in reaberto["backups"])
    # o processo deste teste precisa ver a revisao nova para conferir o banco
    plugins.carregar(pasta / "plugins", forcar=True)
    with pytest.raises(ErroServico, match="termometro_0002"):
        servico.voltar_versao_plugin(master, "termometro", "0.1.0", SENHA)
    assert ("voltar_versao", "ok") in _auditoria(master)
