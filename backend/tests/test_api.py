"""API HTTP local (casca fina): login por token, upload multipart, consultas, exportacao."""

import pytest
from fastapi.testclient import TestClient

from app.api.main import criar_app

from .conftest import N_ARQUIVOS, PASTA_DADOS, SENHA


@pytest.fixture
def cliente(banco, master, cadastro, leitor, equipamento):
    with TestClient(criar_app(iniciar_banco=False)) as c:
        yield c


def _token(cliente, login):
    resposta = cliente.post("/login", json={"login": login, "senha": SENHA})
    assert resposta.status_code == 200, resposta.text
    return {"Authorization": f"Bearer {resposta.json()['token']}"}


def _partes_da_pasta(pasta):
    return [("arquivos", (str(p.relative_to(pasta)), p.read_bytes(), "text/plain"))
            for p in sorted(pasta.rglob("*")) if p.is_file()]


def test_sem_token_e_login_errado(cliente):
    assert cliente.get("/envios").status_code == 401
    assert cliente.post("/login", json={"login": "admin", "senha": "errada"}).status_code == 401
    assert cliente.get("/envios", headers={"Authorization": "Bearer inventado"}).status_code == 401


def test_upload_zip(cliente, equipamento, zip_sd):
    cab = _token(cliente, "cad")
    resposta = cliente.post(f"/equipamentos/{equipamento.id}/envios", headers=cab,
                            files={"arquivos": ("SD.zip", zip_sd.read_bytes(), "application/zip")})
    assert resposta.status_code == 200, resposta.text
    resumo = resposta.json()
    assert (resumo["tipo"], resumo["canal"], resumo["arquivos_recebidos"], resumo["leituras"],
            resumo["corrompidas"], resumo["novas"], resumo["ignorados"]) == ("zip", "upload", 15, 13, 1, 13, 2)
    assert resumo["inicio"] == "2026-10-08T04:08:00" and resumo["fim"] == "2026-10-21T16:00:00"
    # reenviar nao duplica
    resposta = cliente.post(f"/equipamentos/{equipamento.id}/envios", headers=cab,
                            files={"arquivos": ("SD.zip", zip_sd.read_bytes(), "application/zip")})
    assert (resposta.json()["novas"], resposta.json()["duplicadas"]) == (0, N_ARQUIVOS)


def test_upload_pasta_inteira_multipart(cliente, equipamento, pasta_sd):
    partes = _partes_da_pasta(pasta_sd)
    resposta = cliente.post(f"/equipamentos/{equipamento.id}/envios", headers=_token(cliente, "cad"), files=partes)
    assert resposta.status_code == 200, resposta.text
    resumo = resposta.json()
    assert (resumo["tipo"], resumo["arquivos_recebidos"], resumo["novas"], resumo["ignorados"]) == \
        ("pasta", 15, 13, 2)
    assert "Logger/Backup/logger_backup.csv" in resumo["arquivos_ignorados"]


def test_upload_pasta_de_medicao(cliente, equipamento):
    partes = _partes_da_pasta(PASTA_DADOS / "2026101417")
    partes = [(campo, ("2026101417/" + nome, dados, tipo)) for campo, (nome, dados, tipo) in partes]
    resposta = cliente.post(f"/equipamentos/{equipamento.id}/envios", headers=_token(cliente, "cad"), files=partes)
    assert resposta.json()["novas"] == 3


def test_upload_path_traversal(cliente, equipamento):
    resposta = cliente.post(f"/equipamentos/{equipamento.id}/envios", headers=_token(cliente, "cad"),
                            files={"arquivos": ("../../20261008041600.txt", b"x", "text/plain")})
    assert resposta.status_code == 400 and "nao permitido" in resposta.json()["detail"]


def test_leitura_nao_envia_mas_consulta_e_exporta(cliente, equipamento, zip_sd):
    cab = _token(cliente, "ler")
    resposta = cliente.post(f"/equipamentos/{equipamento.id}/envios", headers=cab,
                            files={"arquivos": ("SD.zip", zip_sd.read_bytes(), "application/zip")})
    assert resposta.status_code == 403
    assert cliente.post("/usuarios", headers=_token(cliente, "cad"),
                        json={"login": "x", "nome": "x", "senha": SENHA}).status_code == 403

    resposta = cliente.post(f"/equipamentos/{equipamento.id}/envios/local", headers=_token(cliente, "cad"),
                            json={"caminho": str(zip_sd)})
    assert resposta.json()["canal"] == "local" and resposta.json()["novas"] == N_ARQUIVOS

    assert len(cliente.get("/envios", headers=cab).json()) == 1
    resumo = cliente.get(f"/estacao/equipamentos/{equipamento.id}/resumo", headers=cab).json()
    assert (resumo["leituras"], resumo["corrompidas"]) == (N_ARQUIVOS, 1)
    leituras = cliente.get(f"/estacao/equipamentos/{equipamento.id}/leituras", headers=cab,
                           params={"inicio": "2026-10-08T00:00:00", "fim": "2026-10-08T23:59:59"}).json()
    assert len(leituras) == 7 and leituras[0]["arquivo"] == "20261008040800.txt"

    resposta = cliente.get("/exportar", headers=cab, params={"equipamento_id": equipamento.id, "formato": "csv"})
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert "attachment" in resposta.headers["content-disposition"]
    assert resposta.text.splitlines()[0].startswith("tempo,arquivo,chuva_mm_h")
    assert len(resposta.text.splitlines()) == N_ARQUIVOS     # cabeçalho + as 12 válidas


def test_master_cria_usuario_pela_api(cliente):
    cab = _token(cliente, "admin")
    resposta = cliente.post("/usuarios", headers=cab, json={"login": "novo", "nome": "Novo", "senha": SENHA,
                                                            "perfil": "cadastro"})
    assert resposta.status_code == 200 and resposta.json()["perfil"] == "cadastro"
    resposta = cliente.post("/usuarios", headers=cab, json={"login": "m2", "nome": "M", "senha": SENHA,
                                                            "perfil": "master"})
    assert resposta.status_code == 403
