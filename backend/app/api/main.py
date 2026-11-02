"""API HTTP local. So escuta em 127.0.0.1 (ver app/__main__.py).

    venv/bin/python -m app servidor              # 127.0.0.1:8000
    venv/bin/uvicorn app.api.main:app            # idem (o padrao do uvicorn ja e 127.0.0.1)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .. import servico
from ..nucleo import plugins
from ..nucleo.erros import ErroServico
from ..nucleo.extracao import suporte_rar
from .rotas import rotas


def criar_app(iniciar_banco: bool = True) -> FastAPI:
    """iniciar_banco=False quando o servico ja foi iniciado (testes, app embutido)."""

    @asynccontextmanager
    async def ciclo_de_vida(_app: FastAPI):
        if iniciar_banco:
            servico.iniciar()
        yield
        if iniciar_banco:
            servico.encerrar()

    app = FastAPI(title="Hidrolog - API local", lifespan=ciclo_de_vida)

    @app.exception_handler(ErroServico)
    async def erro_servico(_request: Request, erro: ErroServico):
        cabecalhos = {"WWW-Authenticate": "Bearer"} if erro.status == 401 else None
        return JSONResponse(status_code=erro.status, content={"detail": str(erro)}, headers=cabecalhos)

    @app.get("/saude", tags=["saude"])
    def saude():
        programa, mensagem = suporte_rar()
        return {"rar": {"programa": programa, "mensagem": mensagem},
                "sensores": [p.codigo for p in plugins.todos()]}

    app.include_router(rotas)
    for plugin in plugins.todos():
        rotas_plugin = plugin.rotas() if plugin.rotas else None
        if rotas_plugin is not None:
            app.include_router(rotas_plugin)
    return app


app = criar_app()
