"""Rotas do nucleo: login, usuarios, equipamentos, envios."""

from __future__ import annotations

import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from starlette.datastructures import UploadFile

from .. import servico
from ..nucleo.erros import ErroEnvio
from ..nucleo.tipos import Usuario
from .autenticacao import _bearer, emitir_token, revogar_token, usuario_atual

rotas = APIRouter()


class Login(BaseModel):
    login: str
    senha: str


@rotas.post("/login", tags=["usuarios"])
def login(dados: Login):
    usuario = servico.autenticar(dados.login, dados.senha)
    return {"token": emitir_token(usuario), "usuario": usuario}


@rotas.post("/logout", tags=["usuarios"])
def logout(credenciais: HTTPAuthorizationCredentials = Depends(_bearer)):
    if credenciais is not None:
        revogar_token(credenciais.credentials)
    return {"ok": True}


class NovoUsuario(BaseModel):
    login: str
    nome: str
    senha: str
    perfil: str = "leitura"


class AlteracaoUsuario(BaseModel):
    nome: Optional[str] = None
    perfil: Optional[str] = None
    ativo: Optional[bool] = None


class NovaSenha(BaseModel):
    senha: str


@rotas.get("/usuarios", tags=["usuarios"])
def listar_usuarios(usuario: Usuario = Depends(usuario_atual)):
    return servico.listar_usuarios(usuario)


@rotas.post("/usuarios", tags=["usuarios"])
def criar_usuario(dados: NovoUsuario, usuario: Usuario = Depends(usuario_atual)):
    return servico.criar_usuario(usuario, dados.login, dados.nome, dados.senha, dados.perfil)


@rotas.patch("/usuarios/{usuario_id}", tags=["usuarios"])
def alterar_usuario(usuario_id: int, dados: AlteracaoUsuario, usuario: Usuario = Depends(usuario_atual)):
    return servico.alterar_usuario(usuario, usuario_id, **dados.model_dump(exclude_none=True))


@rotas.put("/usuarios/{usuario_id}/senha", tags=["usuarios"])
def trocar_senha(usuario_id: int, dados: NovaSenha, usuario: Usuario = Depends(usuario_atual)):
    servico.trocar_senha(usuario, usuario_id, dados.senha)
    return {"ok": True}


@rotas.get("/tipos-sensor", tags=["equipamentos"])
def listar_tipos_sensor():
    return servico.listar_tipos_sensor()


class NovoEquipamento(BaseModel):
    tipo_sensor: str
    nome: str
    numero_serie: Optional[str] = None
    local: Optional[str] = None
    observacoes: Optional[str] = None


@rotas.get("/equipamentos", tags=["equipamentos"])
def listar_equipamentos(tipo: Optional[str] = None, usuario: Usuario = Depends(usuario_atual)):
    return servico.listar_equipamentos(usuario, tipo)


@rotas.post("/equipamentos", tags=["equipamentos"])
def criar_equipamento(dados: NovoEquipamento, usuario: Usuario = Depends(usuario_atual)):
    return servico.criar_equipamento(usuario, **dados.model_dump())


@rotas.post("/equipamentos/{equipamento_id}/envios", tags=["envios"])
async def enviar(equipamento_id: int, request: Request, usuario: Usuario = Depends(usuario_atual)):
    """Upload multipart. Cada parte de arquivo (qualquer nome de campo, ex.
    -F arquivos=@...) pode ser um .zip/.rar do SD ou um arquivo de dados
    cujo filename traz o caminho relativo (2026102116/20261021160000.txt),
    para mandar a pasta inteira ou uma pasta de medicao. Um envio so."""
    config = servico.configuracao()
    # o padrao do Starlette e 1000 arquivos por formulario; um SD tem ~11 mil
    async with request.form(max_files=config.max_arquivos, max_fields=100) as formulario:
        partes = [(v.filename or "", v.file) for _, v in formulario.multi_items() if isinstance(v, UploadFile)]
        if not partes:
            raise ErroEnvio("nenhum arquivo no formulario (use -F arquivos=@caminho)")
        return await run_in_threadpool(servico.importar_arquivos, usuario, equipamento_id, partes, canal="upload")


class CaminhoLocal(BaseModel):
    caminho: str


@rotas.post("/equipamentos/{equipamento_id}/envios/local", tags=["envios"])
async def enviar_local(equipamento_id: int, dados: CaminhoLocal, usuario: Usuario = Depends(usuario_atual)):
    """Importa um caminho deste computador, lido no lugar (sem upload)."""
    return await run_in_threadpool(servico.importar_caminho, usuario, equipamento_id, dados.caminho)


@rotas.get("/envios", tags=["envios"])
def listar_envios(equipamento_id: Optional[int] = None, limite: int = Query(100, ge=1, le=1000),
                  usuario: Usuario = Depends(usuario_atual)):
    return servico.listar_envios(usuario, equipamento_id, limite)


@rotas.get("/envios/{envio_id}", tags=["envios"])
def obter_envio(envio_id: int, usuario: Usuario = Depends(usuario_atual)):
    return servico.obter_envio(usuario, envio_id)


@rotas.get("/equipamentos/{equipamento_id}/formatos", tags=["exportacao"])
def listar_formatos(equipamento_id: int, usuario: Usuario = Depends(usuario_atual)):
    return servico.listar_formatos_exportacao(equipamento_id)


@rotas.get("/exportar", tags=["exportacao"])
def exportar(equipamento_id: int, formato: str, tarefas: BackgroundTasks,
             inicio: Optional[datetime] = None, fim: Optional[datetime] = None,
             usuario: Usuario = Depends(usuario_atual)):
    """Gera o arquivo numa pasta temporaria e devolve como download (a pasta
    e apagada depois do envio)."""
    pasta = tempfile.mkdtemp(prefix="hidrolog_exportacao_")
    tarefas.add_task(lambda: shutil.rmtree(pasta, ignore_errors=True))
    try:
        resumo = servico.exportar(usuario, equipamento_id, inicio, fim, formato, pasta)
    except Exception:
        shutil.rmtree(pasta, ignore_errors=True)
        raise
    tipo = {f.codigo: f.tipo_mime for f in servico.listar_formatos_exportacao(equipamento_id)}[formato]
    return FileResponse(resumo.caminho, media_type=tipo, filename=Path(resumo.caminho).name,
                        background=tarefas)
