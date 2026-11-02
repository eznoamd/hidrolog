"""O kit de conformidade (pytest --plugin=<codigo>) passa nos dois plugins de
teste (o sensor de teste e o termometro instalavel) e reprova um plugin que
aceita arquivos de outro sensor."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TESTES = Path(__file__).resolve().parent
PASTAS = {"estacao": TESTES / "sensor_estacao", "termometro": TESTES.parents[1] / "exemplos" / "plugin-termometro"}


def _kit(pasta: Path, codigo: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", HIDROLOG_PROCESSOS="1")
    return subprocess.run([sys.executable, "-m", "pytest", f"--plugin={codigo}", "-q", "-p", "no:cacheprovider"],
                          cwd=pasta, env=env, capture_output=True, text=True, timeout=600)


@pytest.mark.parametrize("codigo", sorted(PASTAS))
def test_plugins_passam_no_kit(codigo):
    r = _kit(PASTAS[codigo], codigo)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    assert " passed" in r.stdout and "failed" not in r.stdout


def test_kit_reprova_plugin_que_aceita_qualquer_coisa(tmp_path):
    copia = tmp_path / "termometro_ruim"
    shutil.copytree(PASTAS["termometro"], copia, ignore=shutil.ignore_patterns("__pycache__"))
    dados = copia / "hidrolog_termometro" / "dados.py"
    texto = dados.read_text()
    texto = texto.replace('''    if not csvs:
        return Recusa("nenhum .csv com a coluna temperatura_c")''', '''    if not csvs:
        return PlanoImportacao([])''')
    dados.write_text(texto)
    r = _kit(copia, "termometro")
    assert r.returncode != 0
    assert "test_reconhecer_recusa_arvore_vazia" in r.stdout and "test_reconhecer_recusa_outro_sensor" in r.stdout
