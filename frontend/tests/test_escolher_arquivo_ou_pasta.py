"""Um botão só para escolher pasta ou arquivo na importação."""

import zipfile

from design.componentes import AreaSoltarArquivo, DialogoArquivoOuPasta


def test_um_botao_so(qapp):
    area = AreaSoltarArquivo()
    assert not hasattr(area, "botao_pasta") and not hasattr(area, "botao_arquivo")
    assert area.botao_escolher.text().strip() == "Escolher…"


def test_dialogo_escolhe_arquivo_ou_pasta(qapp, tmp_path):
    pasta = tmp_path / "sd"
    (pasta / "2026100804").mkdir(parents=True)
    arquivo = tmp_path / "SD.zip"
    with zipfile.ZipFile(arquivo, "w") as z:
        z.writestr("a.txt", "x")

    d = DialogoArquivoOuPasta(None, (".zip", ".rar"))
    d.setDirectory(str(tmp_path))
    d.selectFile(str(arquivo))
    d.accept()
    assert d.escolhido == str(arquivo)

    d = DialogoArquivoOuPasta(None, (".zip", ".rar"))
    d.setDirectory(str(tmp_path))
    d.selectFile(str(pasta))
    d.accept()
    assert d.escolhido == str(pasta)

    # dentro da pasta, sem nada selecionado: escolhe a própria pasta
    d = DialogoArquivoOuPasta(None, (".zip", ".rar"))
    d.setDirectory(str(pasta))
    d.accept()
    assert d.escolhido == str(pasta)
