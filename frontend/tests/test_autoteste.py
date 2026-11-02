"""O autoteste que o instalador do Windows roda no app empacotado também passa
no ambiente de desenvolvimento (banco temporário próprio, sem tela)."""

import os

from hidrolog import autoteste


def test_autoteste_passa(tmp_path, monkeypatch, qapp):
    for var in ("HIDROLOG_DADOS_DIR", "HIDROLOG_MARCA_DIR", "HIDROLOG_PROCESSOS"):
        monkeypatch.setenv(var, os.environ.get(var, ""))      # o autoteste muda; o monkeypatch restaura
    relatorio = tmp_path / "relatorio.txt"
    assert autoteste.executar(str(relatorio)) == 0, relatorio.read_text()
    assert relatorio.read_text().strip().endswith("tudo certo")
