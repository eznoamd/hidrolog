"""Comando de linha (casca fina sobre app.servico):

    venv/bin/python -m app criar-master --login admin [--nome "..."]
    venv/bin/python -m app redefinir-senha --login fulano
    venv/bin/python -m app migrar
    venv/bin/python -m app nova-migracao --sensor <codigo> -m "descricao"
    venv/bin/python -m app importar --login fulano --equipamento 1 CAMINHO [CAMINHO ...]
    venv/bin/python -m app envios --login fulano
    venv/bin/python -m app servidor [--porta 8000]

As senhas sao pedidas no terminal, lidas de HIDROLOG_SENHA ou de um arquivo
(--senha-arquivo, usado pelo instalador: a senha nao aparece na linha de comando).
"""

from __future__ import annotations

import argparse
import getpass
import json
import multiprocessing
import os
import sys
from dataclasses import asdict, is_dataclass


def _senha(confirmar: bool = False, arquivo: str | None = None) -> str:
    if arquivo:
        with open(arquivo, encoding="utf-8-sig") as f:      # o instalador grava com BOM
            return f.read().rstrip("\r\n")
    if os.environ.get("HIDROLOG_SENHA"):
        return os.environ["HIDROLOG_SENHA"]
    senha = getpass.getpass("senha: ")
    if confirmar and getpass.getpass("repita a senha: ") != senha:
        raise SystemExit("as senhas nao conferem")
    return senha


def _mostrar(dados) -> None:
    if isinstance(dados, list):
        dados = [asdict(d) if is_dataclass(d) else d for d in dados]
    elif is_dataclass(dados):
        dados = asdict(dados)
    print(json.dumps(dados, indent=2, ensure_ascii=False, default=str))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app", description="Backend local do Hidrolog")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("criar-master", help="cria o usuario master (so se nao houver nenhum)")
    p.add_argument("--login", required=True)
    p.add_argument("--nome")
    p.add_argument("--senha-arquivo", help="le a senha deste arquivo (primeira linha)")
    p = sub.add_parser("redefinir-senha", help="redefine a senha de um usuario (acesso ao arquivo do banco)")
    p.add_argument("--login", required=True)
    p.add_argument("--senha-arquivo", help="le a senha deste arquivo (primeira linha)")
    sub.add_parser("migrar", help="aplica as migracoes pendentes")
    p = sub.add_parser("nova-migracao", help="gera uma migracao (autogenerate) para o nucleo ou um sensor")
    p.add_argument("--sensor", help="codigo do plugin; sem ele, migracao do nucleo")
    p.add_argument("-m", "--mensagem", required=True)

    p = sub.add_parser("importar", help="importa pasta, pasta de medicao, .zip, .rar ou arquivo")
    p.add_argument("--login", required=True)
    p.add_argument("--equipamento", type=int, required=True, help="id do equipamento")
    p.add_argument("caminhos", nargs="+")
    p = sub.add_parser("envios", help="lista os envios")
    p.add_argument("--login", required=True)
    p.add_argument("--equipamento", type=int)

    p = sub.add_parser("servidor", help="sobe a API local")
    p.add_argument("--porta", type=int, default=8000)

    args = parser.parse_args(argv)

    from . import servico
    from .nucleo.erros import ErroServico

    try:
        if args.comando == "criar-master":
            from .nucleo.administracao import criar_master
            criar_master(servico.banco(), args.login, args.nome or args.login,
                         _senha(confirmar=True, arquivo=args.senha_arquivo))
            print(f"master '{args.login}' criado")
        elif args.comando == "redefinir-senha":
            from .nucleo.administracao import redefinir_senha
            redefinir_senha(servico.banco(), args.login, _senha(confirmar=True, arquivo=args.senha_arquivo))
            print("senha redefinida")
        elif args.comando == "migrar":
            servico.banco()
            print("banco atualizado")
        elif args.comando == "nova-migracao":
            _nova_migracao(args.sensor, args.mensagem)
        elif args.comando == "importar":
            usuario = servico.autenticar(args.login, _senha())
            _mostrar(servico.importar_arquivos(usuario, args.equipamento, args.caminhos))
        elif args.comando == "envios":
            usuario = servico.autenticar(args.login, _senha())
            _mostrar(servico.listar_envios(usuario, args.equipamento))
        elif args.comando == "servidor":
            import uvicorn
            # so localhost: a API nao e para a rede
            uvicorn.run("app.api.main:app", host="127.0.0.1", port=args.porta)
    except ErroServico as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    finally:
        servico.encerrar()
    return 0


def _nova_migracao(sensor, mensagem) -> None:
    """Autogenerate do Alembic contra o banco atual (que precisa estar
    migrado). Para um sensor sem migracao ainda, cria o branch dele."""
    from alembic import command
    from alembic.script import ScriptDirectory

    from . import servico
    from .nucleo import plugins
    from .nucleo.banco import config_alembic

    banco = servico.banco()
    cfg = config_alembic(banco.url)
    if sensor is None:
        command.revision(cfg, mensagem, autogenerate=True, head="nucleo@head")
        return
    plugin = plugins.obter(sensor)
    if plugin.migracoes is None:
        raise SystemExit(f"o plugin {sensor} nao define migracoes")
    plugin.migracoes.mkdir(parents=True, exist_ok=True)
    script = ScriptDirectory.from_config(cfg)
    tem_branch = any(sensor in (r.branch_labels or ()) for r in script.walk_revisions())
    if tem_branch:
        command.revision(cfg, mensagem, autogenerate=True, head=f"{sensor}@head")
    else:
        command.revision(cfg, mensagem, autogenerate=True, head="base", branch_label=sensor,
                         version_path=str(plugin.migracoes), depends_on="nucleo@head")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
