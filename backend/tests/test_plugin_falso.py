"""Um segundo tipo de sensor (tests/plugin_falso) entra so pelo registro de
plugins, com tabela e migracao proprias, sem tocar no nucleo."""

from sqlalchemy import func, inspect, select, text

from app import servico
from sensor_teste.dados import EstacaoLeitura

from .conftest import PASTA_DADOS
from .plugin_falso import FalsoLeitura


def test_tabela_e_migracao_do_plugin(banco):
    assert {"falso_leitura", "estacao_leitura", "equipamento", "envio", "usuario"} <= set(
        inspect(banco.engine).get_table_names())
    with banco.engine.connect() as conexao:
        versoes = {v for (v,) in conexao.execute(text("select version_num from alembic_version"))}
    assert {"estacao_0001", "falso_0001"} <= versoes
    assert "falso" in {t.codigo for t in servico.listar_tipos_sensor()}


def test_importar_no_plugin_falso(cadastro, banco, tmp_path):
    eq = servico.criar_equipamento(cadastro, "falso", "Sensor falso 1")
    pasta = tmp_path / "dados"
    pasta.mkdir()
    (pasta / "falso_20261029120000.csv").write_text("valor;1.5")
    (pasta / "falso_20261029120100.csv").write_text("valor;lixo")
    (pasta / "20261008041600.txt").write_bytes((PASTA_DADOS / "2026100804" / "20261008041600.txt").read_bytes())
    resumo = servico.importar_caminho(cadastro, eq.id, pasta)
    # o .txt da estacao e ignorado: o tipo vem do equipamento escolhido
    assert (resumo.tipo_sensor, resumo.leituras, resumo.novas, resumo.corrompidas, resumo.ignorados) == \
        ("falso", 2, 2, 1, 1)
    assert servico.importar_caminho(cadastro, eq.id, pasta).duplicadas == 2
    with banco.sessao() as sessao:
        assert sessao.scalar(select(func.count(FalsoLeitura.id))) == 2
        assert sessao.scalar(select(func.count(EstacaoLeitura.id))) == 0
    assert servico.listar_formatos_exportacao(eq.id) == []


def test_migracoes_num_caminho_com_espaco(tmp_path, monkeypatch):
    """No Windows o app fica em C:\\Users\\<usuário>\\..., e o nome do usuário pode
    ter espaço: as migrações precisam ser achadas mesmo assim."""
    import shutil

    from app.nucleo import banco as modulo_banco

    destino = tmp_path / "Maria Clara" / "migracoes"
    shutil.copytree(modulo_banco.DIRETORIO_MIGRACOES, destino, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(modulo_banco, "DIRETORIO_MIGRACOES", destino)
    b = modulo_banco.Banco(f"sqlite:///{tmp_path / 'com espaco.db'}")
    assert {"usuario", "tipo_sensor", "equipamento"} <= set(inspect(b.engine).get_table_names())
    b.fechar()
