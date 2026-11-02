"""Camada de servico: o contrato que o app desktop (PySide6) chama direto,
sem HTTP. A API FastAPI e o comando de linha sao cascas finas sobre isto.

Toda funcao (menos autenticar e listar_tipos_sensor) recebe o Usuario
devolvido por autenticar() e confere o perfil dele **no banco** a cada
chamada (um usuario desativado perde o acesso na hora). Perfis:
master > cadastro > leitura. Os retornos sao dataclasses de
app.nucleo.tipos, soltos da sessao do banco. Erros: app.nucleo.erros.

O master nao e criado aqui: so pelo comando `python -m app criar-master`.

Consultas de cada sensor ficam no plugin (Plugin.consultas, ex.
hidrolog_<sensor>.consultas). O nucleo nao conhece nenhum sensor.
"""

from __future__ import annotations

import io
import os
import re
from contextlib import contextmanager
from dataclasses import replace
from datetime import date as date_
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Callable, Iterator, Optional, Sequence, Union

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hidrolog_nucleo.plugin import ContextoExportacao

from .config import Configuracao, instituicao_da_instalacao
from .nucleo import gerenciador, ingestao, modelos, paralelo, plugins, regras
from .nucleo.banco import Banco
from .nucleo.erros import (
    Conflito,
    ErroAutenticacao,
    ErroEnvio,
    ErroPermissao,
    ErroServico,
    ErroValidacao,
    NaoEncontrado,
)
from .nucleo.extracao import Abertura
from .nucleo.seguranca import conferir_senha, exigir, gerar_hash, validar_perfil
from .nucleo.tipos import (
    Equipamento,
    FormatoExportacao,
    InfoOcorrencia,
    InfoPlugin,
    InfoRegra,
    RegistroAuditoria,
    ResumoEnvio,
    ResultadoExportacao,
    ResumoExportacao,
    ResumoLeituras,
    ResumoQualidade,
    TipoSensor,
    Usuario,
)

# item de importar_arquivos: caminho local, ou (nome relativo, bytes ou arquivo binario aberto)
ItemEnvio = Union[str, Path, tuple[str, Union[bytes, BinaryIO]]]

# progresso da importacao: funcao(etapa, feitos, total). Etapas, em ordem:
#   "lendo"          abrindo o envio: arquivos examinados (total None: nao se sabe antes)
#   "interpretando"  unidades do plano do plugin lidas e gravadas (total conhecido;
#                    feitos == total: terminando de gravar)
#   "concluido"      envio gravado (feitos = total = leituras do envio)
# Uma excecao levantada pela funcao interrompe a importacao (nada e gravado).
AoProgresso = Callable[[str, int, Optional[int]], None]
INTERVALO_PROGRESSO_LEITURA = 200   # avisa a cada N arquivos examinados

_banco: Optional[Banco] = None
_config: Optional[Configuracao] = None


# ---------------------------------------------------------------- inicializacao

def iniciar(url: Optional[str] = None, config: Optional[Configuracao] = None) -> Banco:
    """Abre o banco (aplica migracoes) e o torna o banco das funcoes daqui.
    Sem argumentos: DATABASE_URL ou o SQLite no diretorio de dados do
    usuario. Chamar uma vez no inicio do app; se nao chamar, a primeira
    funcao chama sozinha."""
    global _banco, _config
    _config = config or Configuracao.do_ambiente()
    paralelo.configurar(_config.processos)
    plugins.carregar(_config.diretorio_plugins, forcar=True)   # reabrir = descobrir de novo
    if _banco is not None:
        _banco.fechar()
    _banco = Banco(url or _config.database_url)
    with _banco.sessao() as sessao:
        gerenciador.sincronizar(sessao)
    migrar_atributos()
    reavaliar_equipamentos()
    with _banco.sessao() as sessao:
        for caminho in _banco.backups:
            gerenciador.auditar(sessao, None, "migrar", "ok",
                                detalhes=f"migracoes de plugin {', '.join(_banco.migracoes_aplicadas)}; "
                                         f"backup do banco antes: {caminho}")
    return _banco


def encerrar() -> None:
    """Fecha o banco e o pool de processos (chamar ao sair do app)."""
    global _banco
    paralelo.encerrar()
    if _banco is not None:
        _banco.fechar()
        _banco = None


def banco() -> Banco:
    if _banco is None:
        iniciar()
    return _banco


def configuracao() -> Configuracao:
    if _config is None:
        iniciar()
    return _config


def _usuario(u: modelos.Usuario) -> Usuario:
    return Usuario(id=u.id, login=u.login, nome=u.nome, perfil=u.perfil, ativo=u.ativo, criado_em=u.criado_em)


def _equipamento(e: modelos.Equipamento) -> Equipamento:
    return Equipamento(id=e.id, tipo_sensor=e.tipo_sensor, nome=e.nome, numero_serie=e.numero_serie,
                       local=e.local, observacoes=e.observacoes, ativo=e.ativo, criado_em=e.criado_em,
                       latitude=e.latitude, longitude=e.longitude, altitude_m=e.altitude_m,
                       instalado_em=e.instalado_em, atributos=dict(e.atributos or {}), versao_ficha=e.versao_ficha)


def _resumo(envio: modelos.Envio, arquivos_ignorados: Sequence[str] = ()) -> ResumoEnvio:
    return ResumoEnvio(
        id=envio.id, equipamento_id=envio.equipamento_id, equipamento=envio.equipamento.nome,
        tipo_sensor=envio.equipamento.tipo_sensor, usuario=envio.usuario.login,
        recebido_em=envio.recebido_em, canal=envio.canal, tipo=envio.tipo, origem=envio.origem,
        arquivos_recebidos=envio.arquivos_recebidos, ignorados=envio.ignorados, leituras=envio.leituras,
        validas=envio.validas, corrompidas=envio.corrompidas, novas=envio.novas,
        duplicadas=envio.duplicadas, inicio=envio.inicio, fim=envio.fim,
        duracao_s=round(envio.duracao_s, 3),
        avisos=envio.avisos.split("\n") if envio.avisos else [],
        arquivos_ignorados=list(arquivos_ignorados)[:50],
    )


@contextmanager
def sessao_autorizada(usuario: Usuario, perfil: str) -> Iterator[tuple[Session, Usuario]]:
    """Sessao (uma transacao) depois de conferir no banco que o usuario
    existe, esta ativo e tem o perfil. Para uso dos plugins."""
    if not isinstance(usuario, Usuario):
        raise ErroAutenticacao("usuario nao autenticado")
    with banco().sessao() as sessao:
        registro = sessao.get(modelos.Usuario, usuario.id)
        if registro is None or not registro.ativo or registro.login != usuario.login:
            raise ErroAutenticacao("usuario inexistente ou desativado")
        atual = _usuario(registro)
        exigir(atual, perfil)
        yield sessao, atual


def obter_equipamento_orm(sessao: Session, equipamento_id: int, tipo_sensor: Optional[str] = None) -> modelos.Equipamento:
    equipamento = sessao.get(modelos.Equipamento, equipamento_id)
    if equipamento is None:
        raise NaoEncontrado(f"equipamento {equipamento_id} nao encontrado")
    if tipo_sensor is not None and equipamento.tipo_sensor != tipo_sensor:
        raise ErroServico(f"o equipamento '{equipamento.nome}' e do tipo '{equipamento.tipo_sensor}', "
                          f"nao '{tipo_sensor}'")
    return equipamento


# ---------------------------------------------------------------- usuarios

def existe_master() -> bool:
    """True se ja ha um usuario master. Sem master ninguem administra o app:
    a interface pede para rodar `python -m app criar-master`."""
    with banco().sessao() as sessao:
        return sessao.scalar(select(modelos.Usuario.id).where(modelos.Usuario.perfil == "master")) is not None


def autenticar(login: str, senha: str) -> Usuario:
    """Confere login e senha. Erro ErroAutenticacao se errados ou se o usuario estiver desativado."""
    with banco().sessao() as sessao:
        registro = sessao.scalar(select(modelos.Usuario).where(modelos.Usuario.login == (login or "").strip()))
        if registro is None or not conferir_senha(registro.senha_hash, senha or "") or not registro.ativo:
            raise ErroAutenticacao("login ou senha incorretos, ou usuario desativado")
        return _usuario(registro)


def _validar_login(login: str) -> str:
    login = (login or "").strip()
    if not login or any(c.isspace() for c in login):
        raise ErroServico("login vazio ou com espacos")
    return login


def criar_usuario(usuario: Usuario, login: str, nome: str, senha: str, perfil: str = "leitura") -> Usuario:
    """So master. perfil: "cadastro" ou "leitura" (master so pelo comando de linha)."""
    validar_perfil(perfil)
    if perfil == "master":
        raise ErroPermissao("master so e criado pelo comando de linha (python -m app criar-master)")
    login = _validar_login(login)
    with sessao_autorizada(usuario, "master") as (sessao, _):
        if sessao.scalar(select(modelos.Usuario.id).where(modelos.Usuario.login == login)) is not None:
            raise Conflito(f"ja existe o usuario '{login}'")
        novo = modelos.Usuario(login=login, nome=(nome or login).strip(), senha_hash=gerar_hash(senha),
                               perfil=perfil, ativo=True, criado_em=datetime.now())
        sessao.add(novo)
        sessao.flush()
        return _usuario(novo)


def listar_usuarios(usuario: Usuario) -> list[Usuario]:
    """So master."""
    with sessao_autorizada(usuario, "master") as (sessao, _):
        return [_usuario(u) for u in sessao.scalars(select(modelos.Usuario).order_by(modelos.Usuario.login))]


def alterar_usuario(usuario: Usuario, usuario_id: int, *, nome: Optional[str] = None,
                    perfil: Optional[str] = None, ativo: Optional[bool] = None) -> Usuario:
    """So master. Muda nome, perfil ("cadastro"/"leitura") e/ou ativo (False
    desativa). O perfil e o ativo de um master nao mudam por aqui."""
    with sessao_autorizada(usuario, "master") as (sessao, _):
        alvo = sessao.get(modelos.Usuario, usuario_id)
        if alvo is None:
            raise NaoEncontrado(f"usuario {usuario_id} nao encontrado")
        if perfil is not None:
            validar_perfil(perfil)
            if perfil == "master" or (alvo.perfil == "master" and perfil != "master"):
                raise ErroPermissao("o perfil master nao e dado nem retirado pelo app")
            alvo.perfil = perfil
        if ativo is not None:
            if alvo.perfil == "master" and not ativo:
                raise ErroPermissao("um master nao pode ser desativado pelo app")
            alvo.ativo = bool(ativo)
        if nome is not None:
            alvo.nome = nome.strip() or alvo.nome
        return _usuario(alvo)


def trocar_senha(usuario: Usuario, usuario_id: int, nova_senha: str) -> None:
    """So master (de qualquer usuario, inclusive a propria)."""
    with sessao_autorizada(usuario, "master") as (sessao, _):
        alvo = sessao.get(modelos.Usuario, usuario_id)
        if alvo is None:
            raise NaoEncontrado(f"usuario {usuario_id} nao encontrado")
        alvo.senha_hash = gerar_hash(nova_senha)


# ---------------------------------------------------------------- a propria conta (qualquer perfil)

def alterar_meu_nome(usuario: Usuario, nome: str) -> Usuario:
    """Qualquer perfil, so o proprio nome (o login nao muda)."""
    nome = (nome or "").strip()
    if not nome:
        raise ErroServico("o nome nao pode ficar vazio")
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        registro = sessao.get(modelos.Usuario, usuario.id)
        registro.nome = nome
        return _usuario(registro)


def trocar_minha_senha(usuario: Usuario, senha_atual: str, nova_senha: str) -> None:
    """Qualquer perfil, so a propria senha, conferindo a atual. A senha
    atual errada e ErroServico (nao ErroAutenticacao: a sessao continua)."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        registro = sessao.get(modelos.Usuario, usuario.id)
        if not conferir_senha(registro.senha_hash, senha_atual or ""):
            raise ErroServico("a senha atual nao confere")
        if nova_senha == senha_atual:
            raise ErroServico("a nova senha e igual a atual")
        registro.senha_hash = gerar_hash(nova_senha)


def meus_envios(usuario: Usuario, limite: int = 10) -> list[ResumoEnvio]:
    """Qualquer perfil: os envios feitos pelo proprio usuario, mais recentes primeiro."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        consulta = (select(modelos.Envio).where(modelos.Envio.usuario_id == usuario.id)
                    .order_by(modelos.Envio.id.desc()).limit(limite))
        return [_resumo(e) for e in sessao.scalars(consulta)]


# ---------------------------------------------------------------- plugins (gerenciador)

def listar_plugins(usuario: Usuario) -> list[InfoPlugin]:
    """So master. Todos os plugins: os vistos na abertura do app (ativos,
    desativados, incompativeis, com falha, conflitos) e os instalados depois
    (pendentes de reinicio), com origem, hash e versoes guardadas."""
    with sessao_autorizada(usuario, "master") as (sessao, _):
        linhas = list(sessao.scalars(select(modelos.PluginInstalado)))
        logins = {u.id: u.login for u in sessao.scalars(select(modelos.Usuario))}
    por_versao = {(l.codigo, l.versao): l for l in linhas}
    estado = plugins.ler_estado(plugins.diretorio())["plugins"]
    saida: list[InfoPlugin] = []
    vistos = set()
    for s in plugins.situacoes():
        reg = estado.get(s.codigo, {})
        pendente = ""
        if s.estado != "conflito":
            vistos.add(s.codigo)
            if reg.get("versao") and reg["versao"] != s.versao and s.origem != "interno":
                pendente = f"versao {reg['versao']} ativa ao reiniciar"
            elif reg.get("ativo") is False and s.estado == "ativo":
                pendente = "sera desativado ao reiniciar"
            elif reg.get("ativo", True) and s.estado == "desativado":
                pendente = "sera reativado ao reiniciar"
        linha = por_versao.get((s.codigo, s.versao))
        saida.append(InfoPlugin(
            codigo=s.codigo, nome=s.nome, versao=s.versao, contrato=s.contrato, origem=s.origem, estado=s.estado,
            motivo=s.motivo, url=s.url, tag=s.tag, sha256=(linha.sha256 or "") if linha else "",
            caminho=s.caminho, instalado_em=linha.instalado_em if linha else None,
            instalado_por=logins.get(linha.instalado_por, "") if linha else "",
            versoes=gerenciador.versoes_guardadas(s.codigo), pendente=pendente))
    for codigo, reg in sorted(estado.items()):
        if codigo in vistos or not reg.get("versao"):
            continue
        linha = por_versao.get((codigo, reg["versao"]))
        saida.append(InfoPlugin(
            codigo=codigo, nome=linha.nome if linha else codigo, versao=reg["versao"],
            contrato=linha.contrato if linha else "?", origem=reg.get("origem", "pasta"), estado="instalado",
            url=reg.get("url", ""), tag=reg.get("tag", ""), sha256=reg.get("sha256", ""),
            instalado_em=linha.instalado_em if linha else None,
            instalado_por=logins.get(linha.instalado_por, "") if linha else "",
            versoes=gerenciador.versoes_guardadas(codigo),
            pendente="reinicie o Hidrolog para ativar" if reg.get("ativo", True) else "desativado"))
    return saida


def _auditar(usuario: Usuario, acao: str, resultado: str, **campos) -> None:
    with banco().sessao() as sessao:
        gerenciador.auditar(sessao, usuario, acao, resultado, **campos)


def preparar_plugin(usuario: Usuario, origem: str, caminho: Optional[Union[str, Path]] = None,
                    url: Optional[str] = None, tag: Optional[str] = None,
                    baixar: Optional[Callable[[str], bytes]] = None,
                    base_github: str = "https://github.com") -> "gerenciador.PacotePreparado":
    """So master. Passo 1 da importacao de um plugin: copia (pasta, .zip) ou
    baixa (GitHub: url + tag/release) para uma pasta temporaria e valida sem
    executar nada do plugin (manifesto, contrato, codigo, dependencias,
    limites). Devolve o que vai entrar, com o hash, para a confirmacao.
    `baixar(url) -> bytes` troca o download (testes sem rede)."""
    with sessao_autorizada(usuario, "master"):
        pass
    try:
        return gerenciador.preparar(origem, str(caminho) if caminho else None, url, tag, baixar, base_github,
                                    usuario.id)
    except ErroServico as erro:
        _auditar(usuario, "importar", "recusado", origem=origem,
                 detalhes=f"{url or caminho or ''}{' @ ' + tag if tag else ''}: {erro}")
        raise


def cancelar_plugin(usuario: Usuario, token: str) -> None:
    """So master. Descarta uma preparacao (o usuario desistiu)."""
    with sessao_autorizada(usuario, "master"):
        pass
    gerenciador.descartar(token)


def instalar_plugin(usuario: Usuario, token: str, senha: str) -> str:
    """So master, com a senha conferida de novo (3 erradas cancelam). Copia
    o plugin preparado para a pasta de plugins do app e o marca como ativo.
    Ele entra na proxima abertura do app (reinicie para ativar)."""
    with sessao_autorizada(usuario, "master"):
        pass
    pacote, raiz = gerenciador.obter_preparado(token, usuario.id)
    acao = "atualizar" if pacote.atualizacao else "importar"
    gerenciador.conferir_senha(banco(), usuario, senha, ("instalar", token), acao, pacote.codigo, pacote.versao,
                               ao_cancelar=lambda: gerenciador.descartar(token))
    try:
        with sessao_autorizada(usuario, "master") as (sessao, _):
            destino = gerenciador.instalar(sessao, usuario, pacote, raiz)
            gerenciador.auditar(sessao, usuario, acao, "ok", pacote.codigo, pacote.versao, pacote.origem,
                                f"{pacote.origem_legivel} · sha256 {pacote.sha256} · {destino}")
    except ErroServico as erro:
        _auditar(usuario, acao, "erro", codigo=pacote.codigo, versao=pacote.versao, origem=pacote.origem,
                 detalhes=str(erro))
        raise
    finally:
        gerenciador.descartar(token)
    return f"plugin {pacote.nome} {pacote.versao} instalado. Reinicie o Hidrolog para ativar."


def _acao_plugin(usuario: Usuario, codigo: str, senha: str, acao: str, executar) -> None:
    with sessao_autorizada(usuario, "master"):
        pass
    gerenciador.conferir_senha(banco(), usuario, senha, (acao, codigo), acao, codigo)
    with sessao_autorizada(usuario, "master") as (sessao, _):
        detalhes = executar(sessao)
        gerenciador.auditar(sessao, usuario, acao, "ok", codigo, detalhes=detalhes)


def desativar_plugin(usuario: Usuario, codigo: str, senha: str) -> str:
    """So master, com senha. O plugin deixa de carregar na proxima abertura;
    os dados dele ficam no banco (os equipamentos aparecem como "plugin ausente")."""
    _acao_plugin(usuario, codigo, senha, "desativar",
                 lambda sessao: gerenciador.definir_ativo(sessao, codigo, False) or "os dados ficam no banco")
    return f"plugin {codigo} desativado. Reinicie o Hidrolog para aplicar; os dados continuam no banco."


def reativar_plugin(usuario: Usuario, codigo: str, senha: str) -> str:
    """So master, com senha."""
    _acao_plugin(usuario, codigo, senha, "reativar", lambda sessao: gerenciador.definir_ativo(sessao, codigo, True))
    return f"plugin {codigo} reativado. Reinicie o Hidrolog para aplicar."


def voltar_versao_plugin(usuario: Usuario, codigo: str, versao: str, senha: str) -> str:
    """So master, com senha. Ativa uma versao guardada; recusado se a versao
    atual ja aplicou migracoes que a anterior nao conhece."""
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from .nucleo.banco import _aplicadas, config_alembic

    def executar(sessao):
        script = ScriptDirectory.from_config(config_alembic(banco().url))
        with banco().engine.connect() as conexao:
            aplicadas = _aplicadas(script, MigrationContext.configure(conexao).get_current_heads())
        gerenciador.trocar_versao(sessao, codigo, versao, aplicadas)
        return f"versao {versao} ativa ao reiniciar"

    _acao_plugin(usuario, codigo, senha, "voltar_versao", executar)
    return f"plugin {codigo}: a versao {versao} fica ativa ao reiniciar o Hidrolog."


def definir_github_confiaveis(usuario: Usuario, repositorios: Sequence[str], senha: str) -> list[str]:
    """So master, com senha. Lista confiavel do GitHub (organizacoes ou
    repositorios). Vazia = qualquer repositorio, sempre com aviso e senha."""
    resultado: list[str] = []

    def executar(_sessao):
        resultado.extend(gerenciador.definir_confiaveis(list(repositorios)))
        return "lista confiavel: " + (", ".join(resultado) or "desligada")

    _acao_plugin(usuario, "", senha, "lista_confiavel", executar)
    return resultado


def github_confiaveis(usuario: Usuario) -> list[str]:
    """So master."""
    with sessao_autorizada(usuario, "master"):
        pass
    return list(plugins.ler_estado(plugins.diretorio()).get("github_confiaveis", []))


def listar_auditoria_plugins(usuario: Usuario, limite: int = 200) -> list[RegistroAuditoria]:
    """So master. Mais recentes primeiro."""
    with sessao_autorizada(usuario, "master") as (sessao, _):
        consulta = select(modelos.AuditoriaPlugin).order_by(modelos.AuditoriaPlugin.id.desc()).limit(limite)
        return [RegistroAuditoria(a.id, a.quando, a.login, a.acao, a.codigo, a.versao, a.origem, a.resultado,
                                  a.detalhes) for a in sessao.scalars(consulta)]


# ---------------------------------------------------------------- sensores e equipamentos

def listar_tipos_sensor(incluir_ausentes: bool = False) -> list[TipoSensor]:
    """Tipos de sensor com plugin carregado. incluir_ausentes: tambem os que
    ja existiram no banco e cujo plugin nao esta carregado (desativado ou removido)."""
    tipos = {p.codigo: TipoSensor(codigo=p.codigo, nome=p.nome) for p in plugins.todos()}
    if incluir_ausentes:
        with banco().sessao() as sessao:
            for t in sessao.scalars(select(modelos.TipoSensor)):
                tipos.setdefault(t.codigo, TipoSensor(codigo=t.codigo, nome=t.nome))
    return sorted(tipos.values(), key=lambda t: t.codigo)


def listar_equipamentos(usuario: Usuario, tipo: Optional[str] = None,
                        incluir_inativos: bool = False) -> list[Equipamento]:
    """Leitura+. tipo: codigo do tipo de sensor (ex. "pluviometro")."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        consulta = select(modelos.Equipamento).order_by(modelos.Equipamento.nome)
        if tipo is not None:
            consulta = consulta.where(modelos.Equipamento.tipo_sensor == tipo)
        if not incluir_inativos:
            consulta = consulta.where(modelos.Equipamento.ativo.is_(True))
        return [_equipamento(e) for e in sessao.scalars(consulta)]


def obter_equipamento(usuario: Usuario, equipamento_id: int) -> Equipamento:
    """Leitura+."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        return _equipamento(obter_equipamento_orm(sessao, equipamento_id))


# limites dos campos comuns da ficha (validados aqui, no backend)
_LIMITES_COMUNS = {"latitude": (-90.0, 90.0, "graus"), "longitude": (-180.0, 180.0, "graus"),
                   "altitude_m": (-500.0, 9000.0, "m")}
_NAO_MUDA = object()


def ficha_do_tipo(tipo_sensor: str) -> list:
    """Campos da ficha que o plugin do tipo acrescenta ao cadastro
    (hidrolog_nucleo.plugin.Campo). Sem plugin carregado: lista vazia."""
    plugin = plugins.talvez(tipo_sensor)
    return list(plugin.ficha) if plugin is not None else []


def _validar_comuns(valores: dict, erros: dict) -> dict:
    saida = {}
    for chave, valor in valores.items():
        if valor is _NAO_MUDA:
            continue
        if chave in _LIMITES_COMUNS:
            if valor is None or (isinstance(valor, str) and not valor.strip()):
                saida[chave] = None
                continue
            try:
                numero = float(str(valor).strip().replace(",", ".")) if isinstance(valor, str) else float(valor)
            except (TypeError, ValueError):
                erros[chave] = "numero invalido"
                continue
            minimo, maximo, unidade = _LIMITES_COMUNS[chave]
            if not (minimo <= numero <= maximo):
                erros[chave] = f"use um valor entre {minimo:g} e {maximo:g} {unidade}"
                continue
            saida[chave] = numero
        elif chave == "instalado_em":
            if valor is None or (isinstance(valor, str) and not valor.strip()):
                saida[chave] = None
            elif isinstance(valor, datetime):
                saida[chave] = valor.date()
            elif isinstance(valor, date_):
                saida[chave] = valor
            else:
                texto = str(valor).strip()
                try:
                    saida[chave] = (datetime.strptime(texto, "%d/%m/%Y").date() if "/" in texto
                                    else date_.fromisoformat(texto))
                except ValueError:
                    erros[chave] = "data invalida (use dd/mm/aaaa)"
                    continue
                if saida[chave] > date_.today():
                    erros[chave] = "a data de instalacao nao pode estar no futuro"
    return saida


def _aplicar_ficha(equipamento: modelos.Equipamento, atributos, comuns: dict) -> None:
    """Valida e grava os campos comuns e os atributos da ficha do plugin.
    Erros de todos os campos juntos num ErroValidacao(campos={...})."""
    erros: dict[str, str] = {}
    validos = _validar_comuns(comuns, erros)
    novos_atributos = None
    if atributos is not _NAO_MUDA and atributos is not None:
        plugin = plugins.talvez(equipamento.tipo_sensor)
        if plugin is None:
            erros["atributos"] = ("o plugin deste tipo de sensor nao esta carregado: a ficha especifica "
                                  "nao pode ser alterada agora")
        else:
            from hidrolog_nucleo.plugin import validar_ficha

            try:
                novos_atributos = validar_ficha(plugin.ficha, atributos, equipamento.atributos or {})
            except ErroValidacao as erro:
                erros.update(erro.campos)
            else:
                equipamento.versao_ficha = plugin.versao_ficha
    if erros:
        raise ErroValidacao("valores invalidos: " + "; ".join(f"{k}: {v}" for k, v in erros.items()), campos=erros)
    for chave, valor in validos.items():
        setattr(equipamento, chave, valor)
    if novos_atributos is not None:
        equipamento.atributos = novos_atributos


def criar_equipamento(usuario: Usuario, tipo_sensor: str, nome: str, numero_serie: Optional[str] = None,
                      local: Optional[str] = None, observacoes: Optional[str] = None, *,
                      latitude=None, longitude=None, altitude_m=None, instalado_em=None,
                      atributos: Optional[dict] = None) -> Equipamento:
    """Cadastro+. tipo_sensor: codigo de listar_tipos_sensor(). nome unico.
    Campos comuns opcionais (coordenadas, altitude, data de instalacao) e
    `atributos`: a ficha do plugin do tipo (ficha_do_tipo), validada aqui;
    os campos ausentes recebem o padrao da ficha. Erro: ErroValidacao(campos)."""
    plugin = plugins.obter(tipo_sensor)
    nome = (nome or "").strip()
    if not nome:
        raise ErroValidacao("o equipamento precisa de um nome", campos={"nome": "informe o nome"})
    with sessao_autorizada(usuario, "cadastro") as (sessao, _):
        if sessao.scalar(select(modelos.Equipamento.id).where(modelos.Equipamento.nome == nome)) is not None:
            raise Conflito(f"ja existe o equipamento '{nome}'")
        equipamento = modelos.Equipamento(tipo_sensor=tipo_sensor, nome=nome, numero_serie=numero_serie,
                                          local=local, observacoes=observacoes, ativo=True,
                                          criado_em=datetime.now(), atributos={},
                                          versao_ficha=plugin.versao_ficha)
        _aplicar_ficha(equipamento, atributos or {},
                       dict(latitude=latitude, longitude=longitude, altitude_m=altitude_m, instalado_em=instalado_em))
        sessao.add(equipamento)
        sessao.flush()
        return _equipamento(equipamento)


def alterar_equipamento(usuario: Usuario, equipamento_id: int, *, nome: Optional[str] = None,
                        numero_serie: Optional[str] = None, local: Optional[str] = None,
                        observacoes: Optional[str] = None, ativo: Optional[bool] = None,
                        latitude=_NAO_MUDA, longitude=_NAO_MUDA, altitude_m=_NAO_MUDA, instalado_em=_NAO_MUDA,
                        atributos: Optional[dict] = None) -> Equipamento:
    """Cadastro+. So muda os campos passados (o tipo de sensor nao muda).
    Coordenadas/altitude/instalacao: None apaga. atributos: os campos da
    ficha a mudar (os outros ficam); os de origem "leituras" nao mudam por aqui."""
    with sessao_autorizada(usuario, "cadastro") as (sessao, _):
        equipamento = obter_equipamento_orm(sessao, equipamento_id)
        if nome is not None and nome.strip() and nome.strip() != equipamento.nome:
            if sessao.scalar(select(modelos.Equipamento.id).where(modelos.Equipamento.nome == nome.strip())):
                raise Conflito(f"ja existe o equipamento '{nome.strip()}'")
            equipamento.nome = nome.strip()
        _aplicar_ficha(equipamento, atributos if atributos is not None else _NAO_MUDA,
                       dict(latitude=latitude, longitude=longitude, altitude_m=altitude_m, instalado_em=instalado_em))
        for campo, valor in (("numero_serie", numero_serie), ("local", local), ("observacoes", observacoes)):
            if valor is not None:
                setattr(equipamento, campo, valor or None)
        if ativo is not None:
            equipamento.ativo = bool(ativo)
        return _equipamento(equipamento)


def _atualizar_atributos_das_leituras(sessao: Session, equipamento: modelos.Equipamento, plugin,
                                      metadados: dict) -> None:
    """Campos da ficha com origem="leituras": o valor mais recente nao nulo da
    coluna do plugin (ou o metadado do envio com a mesma chave)."""
    campos = [c for c in plugin.ficha if c.origem == "leituras"]
    if not campos:
        return
    tabela = plugin.ingestao.tabela
    tempo = getattr(tabela, plugin.ingestao.coluna_tempo)
    atributos = dict(equipamento.atributos or {})
    for campo in campos:
        valor = None
        coluna = getattr(tabela, campo.coluna, None) if campo.coluna else None
        if coluna is not None:
            valor = sessao.scalar(select(coluna).where(tabela.equipamento_id == equipamento.id, coluna.isnot(None))
                                  .order_by(tempo.desc()).limit(1))
        if valor is None:
            valor = metadados.get(campo.chave)
        if valor is not None:
            atributos[campo.chave] = valor.strip() if isinstance(valor, str) else valor
    if atributos != (equipamento.atributos or {}):
        equipamento.atributos = atributos


def migrar_atributos() -> int:
    """Ao abrir: equipamentos com a ficha numa versao antiga passam pela
    migracao de atributos do plugin (Plugin.migrar_atributos). Devolve quantos."""
    n = 0
    with banco().sessao() as sessao:
        for plugin in plugins.todos():
            if plugin.migrar_atributos is None:
                continue
            for e in sessao.scalars(select(modelos.Equipamento).where(
                    modelos.Equipamento.tipo_sensor == plugin.codigo)):
                if (e.versao_ficha or 0) < plugin.versao_ficha:
                    e.atributos = plugin.migrar_atributos(dict(e.atributos or {}), e.versao_ficha or 0)
                    e.versao_ficha = plugin.versao_ficha
                    n += 1
    return n


# ---------------------------------------------------------------- envios

def _tipo_envio(tipos: list[str], tem_pasta: bool) -> str:
    unicos = set(tipos)
    if len(unicos) == 1:
        tipo = unicos.pop()
        return "pasta" if tipo == "arquivos" and tem_pasta else tipo
    return "misto"


def _origem(nomes: list[str]) -> str:
    texto = "; ".join(nomes[:5])
    return texto + (f"; ... (+{len(nomes) - 5})" if len(nomes) > 5 else "")


def importar_arquivos(usuario: Usuario, equipamento_id: int, arquivos: Sequence[ItemEnvio],
                      *, canal: Optional[str] = None, origem: Optional[str] = None,
                      ao_progresso: Optional[AoProgresso] = None) -> ResumoEnvio:
    """Cadastro+. Importa um envio para o equipamento. Cada item e um
    caminho local (pasta do SD, pasta de medicao, .zip, .rar, arquivo
    solto), lido no lugar sem copia, ou um par (nome relativo, bytes ou
    arquivo binario aberto), como num upload. Tudo vira um envio so, numa
    transacao: ou entra tudo, ou nada.

    Ingestao em tres camadas: o nucleo abre os itens e monta a arvore de
    arquivos; o plugin do tipo do equipamento reconhece a estrutura (plano de
    importacao, ou recusa com o motivo: EnvioRecusado) e le as unidades; o
    nucleo grava, deduplicando pela chave do plugin. Os arquivos que o plugin
    deixa de fora contam como ignorados.

    ao_progresso: opcional, funcao(etapa, feitos, total) chamada na thread
    de quem importa (ver AoProgresso). Se ela levantar uma excecao, a
    importacao para e nada e gravado."""
    if not arquivos:
        raise ErroEnvio("nenhum arquivo enviado")
    config = configuracao()
    inicio = datetime.now()

    with sessao_autorizada(usuario, "cadastro") as (sessao, atual):
        equipamento = obter_equipamento_orm(sessao, equipamento_id)
        if not equipamento.ativo:
            raise ErroServico(f"o equipamento '{equipamento.nome}' esta desativado")
        plugin = plugins.talvez(equipamento.tipo_sensor)
        if plugin is None:
            # sem o plugin nao ha quem reconheca e leia os arquivos; o que ja foi
            # importado continua no banco (consulta e exportacao generica)
            raise ErroServico(f"o tipo de sensor de '{equipamento.nome}' esta sem plugin carregado: "
                              "reative ou instale o plugin para importar dados")

    with Abertura(config) as abertura:
        for item in arquivos:
            if isinstance(item, tuple):
                nome, conteudo = item
                if isinstance(conteudo, (bytes, bytearray)):
                    conteudo = io.BytesIO(conteudo)
                abertura.adicionar_parte(nome, conteudo)
                canal = canal or "upload"
            else:
                abertura.adicionar_caminho(item)
                canal = canal or "local"
            if ao_progresso is not None:
                ao_progresso("lendo", abertura.contador.arquivos, None)
        plano = ingestao.reconhecer(plugin, abertura.arvore)

        def _interpretando(feitos: int, total: int) -> None:
            ao_progresso("interpretando", feitos, total)

        try:
            with sessao_autorizada(usuario, "cadastro") as (sessao, atual):
                envio = modelos.Envio(
                    equipamento_id=equipamento_id, usuario_id=atual.id, recebido_em=inicio, canal=canal,
                    tipo=_tipo_envio(abertura.tipos, abertura.tem_pasta),
                    origem=origem or _origem(abertura.nomes),
                    arquivos_recebidos=abertura.contador.arquivos, ignorados=0)
                sessao.add(envio)
                sessao.flush()
                eq_dados = _equipamento(envio.equipamento)
                n_ocorrencias = [0]

                def _regras_de_leitura(linhas: list[dict]) -> None:
                    n_ocorrencias[0] += regras.rodar_leitura(sessao, plugin, eq_dados, envio.id, linhas)

                with paralelo.informar_progresso(_interpretando if ao_progresso is not None else None):
                    resultado = ingestao.importar(sessao, envio, plugin, plano,
                                                  plugins.caminho_importacao(plugin.codigo), _regras_de_leitura)
                for campo in ("ignorados", "leituras", "validas", "corrompidas", "novas", "duplicadas",
                              "inicio", "fim"):
                    setattr(envio, campo, getattr(resultado, campo))
                _atualizar_atributos_das_leituras(sessao, envio.equipamento, plugin, resultado.metadados)
                envio.avisos = "\n".join(resultado.avisos) or None
                sessao.flush()
                eq_dados = _equipamento(envio.equipamento)
                if resultado.novas:
                    n_ocorrencias[0] += regras.rodar_envio(sessao, plugin, eq_dados, _resumo(envio),
                                                           resultado.inicio, resultado.fim)
                regras.rodar_equipamento(sessao, plugin, eq_dados)
                envio.duracao_s = (datetime.now() - inicio).total_seconds()
                sessao.flush()
                resumo = replace(_resumo(envio, resultado.arquivos_ignorados), ocorrencias=n_ocorrencias[0])
        except IntegrityError as erro:
            raise Conflito("conflito com outra importacao simultanea do mesmo equipamento; envie de novo") from erro
    if ao_progresso is not None:
        ao_progresso("concluido", resumo.leituras, resumo.leituras)
    return resumo


def sugerir_tipo(itens: Sequence[ItemEnvio]) -> list[TipoSensor]:
    """Tipos de sensor cujo plugin reconhece o envio (reconhecer em modo de
    verificacao, que so olha a estrutura). A escolha final e do usuario."""
    config = configuracao()
    saida = []
    with Abertura(config) as abertura:
        for item in itens:
            if isinstance(item, tuple):
                nome, conteudo = item
                abertura.adicionar_parte(nome, io.BytesIO(conteudo) if isinstance(conteudo, (bytes, bytearray))
                                         else conteudo)
            else:
                abertura.adicionar_caminho(item)
        for plugin in plugins.todos():
            try:
                plano = ingestao.reconhecer(plugin, abertura.arvore, verificar=True)
            except ErroServico:
                continue
            except Exception:  # noqa: BLE001 - um plugin com defeito nao atrapalha a sugestao
                continue
            if plano.unidades:
                saida.append(TipoSensor(codigo=plugin.codigo, nome=plugin.nome))
    return saida


def importar_caminho(usuario: Usuario, equipamento_id: int, caminho: Union[str, Path],
                     ao_progresso: Optional[AoProgresso] = None) -> ResumoEnvio:
    """Cadastro+. Importa um caminho local (pasta do SD, pasta de medicao,
    .zip, .rar ou arquivo solto), lido no lugar, sem copia. ao_progresso:
    ver importar_arquivos."""
    return importar_arquivos(usuario, equipamento_id, [caminho], ao_progresso=ao_progresso)


def listar_envios(usuario: Usuario, equipamento_id: Optional[int] = None, limite: int = 100) -> list[ResumoEnvio]:
    """Leitura+. Mais recentes primeiro."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        consulta = select(modelos.Envio).order_by(modelos.Envio.id.desc()).limit(limite)
        if equipamento_id is not None:
            consulta = consulta.where(modelos.Envio.equipamento_id == equipamento_id)
        return [_resumo(e) for e in sessao.scalars(consulta)]


def obter_envio(usuario: Usuario, envio_id: int) -> ResumoEnvio:
    """Leitura+."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        envio = sessao.get(modelos.Envio, envio_id)
        if envio is None:
            raise NaoEncontrado(f"envio {envio_id} nao encontrado")
        return _resumo(envio)


# ---------------------------------------------------------------- qualidade (regras e ocorrencias)

def reavaliar_equipamentos(equipamento_id: Optional[int] = None) -> int:
    """Roda as regras de nivel equipamento (ao abrir o app; depois de cada
    envio isso ja acontece). Devolve quantas ocorrencias ficaram abertas."""
    abertas = 0
    with banco().sessao() as sessao:
        consulta = select(modelos.Equipamento).where(modelos.Equipamento.ativo.is_(True))
        if equipamento_id is not None:
            consulta = select(modelos.Equipamento).where(modelos.Equipamento.id == equipamento_id)
        for e in sessao.scalars(consulta):
            plugin = plugins.talvez(e.tipo_sensor)
            if plugin is not None:
                abertas += regras.rodar_equipamento(sessao, plugin, _equipamento(e))
    return abertas


def listar_regras(usuario: Usuario, equipamento_id: int) -> list[InfoRegra]:
    """Leitura+. As regras do plugin do tipo do equipamento, com os
    parametros valendo para ele (padrao + ajustes) e quem ajustou."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        equipamento = obter_equipamento_orm(sessao, equipamento_id)
        plugin = plugins.talvez(equipamento.tipo_sensor)
        if plugin is None:
            return []
        config = regras.configuracoes(sessao, equipamento_id)
        logins = {u.id: u.login for u in sessao.scalars(select(modelos.Usuario))}
        saida = []
        for r in plugin.regras:
            c = config.get(r.codigo)
            parametros, ativa = regras.efetivos(r, c)
            saida.append(InfoRegra(r.codigo, r.descricao, r.nivel, r.severidade, parametros, dict(r.parametros),
                                   ativa, r.declarativa, dict(r.ajuda_parametros),
                                   logins.get(c.alterada_por, "") if c else "", c.alterada_em if c else None))
        return saida


def configurar_regra(usuario: Usuario, equipamento_id: int, codigo: str, parametros: Optional[dict] = None,
                     ativa: Optional[bool] = None) -> InfoRegra:
    """Cadastro+. Ajusta os parametros de uma regra (ou a desliga) so para
    este equipamento, registrando quem alterou. Os parametros sao conferidos
    contra os da regra (nomes e tipo numerico). Erro: ErroValidacao(campos)."""
    with sessao_autorizada(usuario, "cadastro") as (sessao, atual):
        equipamento = obter_equipamento_orm(sessao, equipamento_id)
        plugin = plugins.obter(equipamento.tipo_sensor)
        regra = next((r for r in plugin.regras if r.codigo == codigo), None)
        if regra is None:
            raise NaoEncontrado(f"regra {codigo!r} nao existe para {plugin.codigo}")
        config = sessao.scalar(select(modelos.RegraConfig).where(
            modelos.RegraConfig.equipamento_id == equipamento_id, modelos.RegraConfig.codigo_regra == codigo))
        novos = dict(config.parametros or {}) if config else {}
        erros = {}
        for chave, valor in (parametros or {}).items():
            if chave not in regra.parametros:
                erros[chave] = "parametro desconhecido para esta regra"
                continue
            padrao = regra.parametros[chave]
            try:
                if isinstance(padrao, bool):
                    valor = bool(valor)
                elif isinstance(padrao, int):
                    numero = float(str(valor).replace(",", ".")) if isinstance(valor, str) else float(valor)
                    if numero != int(numero):
                        raise ValueError
                    valor = int(numero)
                elif isinstance(padrao, float):
                    valor = float(str(valor).replace(",", ".")) if isinstance(valor, str) else float(valor)
            except (TypeError, ValueError):
                erros[chave] = "numero invalido"
                continue
            if isinstance(valor, (int, float)) and not isinstance(valor, bool) and valor < 0:
                erros[chave] = "use um valor maior ou igual a zero"
                continue
            if valor == padrao:
                novos.pop(chave, None)
            else:
                novos[chave] = valor
        if erros:
            raise ErroValidacao("parametros invalidos: " + "; ".join(f"{k}: {v}" for k, v in erros.items()),
                                campos=erros)
        if config is None:
            config = modelos.RegraConfig(equipamento_id=equipamento_id, codigo_regra=codigo, ativa=True,
                                         alterada_em=datetime.now())
            sessao.add(config)
        config.parametros = novos
        if ativa is not None:
            config.ativa = bool(ativa)
        config.alterada_por = atual.id
        config.alterada_em = datetime.now()
        sessao.flush()
        if regra.nivel == "equipamento":
            regras.rodar_equipamento(sessao, plugin, _equipamento(equipamento))
    return next(r for r in listar_regras(usuario, equipamento_id) if r.codigo == codigo)


def _ocorrencia(o: modelos.Ocorrencia, nomes: dict, logins: dict) -> InfoOcorrencia:
    return InfoOcorrencia(o.id, o.equipamento_id, nomes.get(o.equipamento_id, ""), o.envio_id, o.tempo,
                          o.codigo_regra, o.nivel, o.severidade, o.mensagem, o.criada_em, o.resolvida_em,
                          logins.get(o.resolvida_por, "") if o.resolvida_por else "")


def listar_ocorrencias(usuario: Usuario, equipamento_id: Optional[int] = None, abertas: Optional[bool] = True,
                       nivel: Optional[str] = None, limite: int = 1000) -> list[InfoOcorrencia]:
    """Leitura+. Ocorrencias de qualidade, mais graves e recentes primeiro.
    abertas: True (padrao) so as abertas, False so as resolvidas, None todas."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        consulta = select(modelos.Ocorrencia)
        if equipamento_id is not None:
            consulta = consulta.where(modelos.Ocorrencia.equipamento_id == equipamento_id)
        if abertas is True:
            consulta = consulta.where(modelos.Ocorrencia.resolvida_em.is_(None))
        elif abertas is False:
            consulta = consulta.where(modelos.Ocorrencia.resolvida_em.isnot(None))
        if nivel is not None:
            consulta = consulta.where(modelos.Ocorrencia.nivel == nivel)
        consulta = consulta.order_by(modelos.Ocorrencia.id.desc()).limit(limite)
        nomes = {e.id: e.nome for e in sessao.scalars(select(modelos.Equipamento))}
        logins = {u.id: u.login for u in sessao.scalars(select(modelos.Usuario))}
        ordem = {"alerta": 0, "suspeita": 1, "aviso": 2}
        saida = [_ocorrencia(o, nomes, logins) for o in sessao.scalars(consulta)]
        return sorted(saida, key=lambda o: (o.resolvida_em is not None, ordem.get(o.severidade, 3), -o.id))


def resumo_qualidade(usuario: Usuario) -> dict[int, ResumoQualidade]:
    """Leitura+. Ocorrencias abertas por equipamento e severidade (selo na
    lista de equipamentos e cartao de alertas do Inicio)."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        contagens: dict[int, dict] = {}
        for eq_id, severidade, n in sessao.execute(
                select(modelos.Ocorrencia.equipamento_id, modelos.Ocorrencia.severidade, func.count())
                .where(modelos.Ocorrencia.resolvida_em.is_(None))
                .group_by(modelos.Ocorrencia.equipamento_id, modelos.Ocorrencia.severidade)):
            contagens.setdefault(eq_id, {})[severidade] = n
        return {eq_id: ResumoQualidade(eq_id, c.get("alerta", 0), c.get("suspeita", 0), c.get("aviso", 0))
                for eq_id, c in contagens.items()}


def resolver_ocorrencia(usuario: Usuario, ocorrencia_id: int) -> InfoOcorrencia:
    """Cadastro+. Marca a ocorrencia como resolvida (vista e tratada). Os
    dados nao mudam. Uma ocorrencia de equipamento volta se a condicao ainda valer."""
    with sessao_autorizada(usuario, "cadastro") as (sessao, atual):
        o = sessao.get(modelos.Ocorrencia, ocorrencia_id)
        if o is None:
            raise NaoEncontrado(f"ocorrencia {ocorrencia_id} nao encontrada")
        if o.resolvida_em is None:
            o.resolvida_em = datetime.now()
            o.resolvida_por = atual.id
        nomes = {o.equipamento_id: sessao.get(modelos.Equipamento, o.equipamento_id).nome}
        return _ocorrencia(o, nomes, {atual.id: atual.login})


def tempos_suspeitos(usuario: Usuario, equipamento_id: int, inicio: Optional[datetime] = None,
                     fim: Optional[datetime] = None) -> set:
    """Leitura+. Tempos das leituras com ocorrencia de severidade "suspeita"
    ainda aberta (os graficos destacam; o filtro "ocultar suspeitas" tira)."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        consulta = select(modelos.Ocorrencia.tempo).where(
            modelos.Ocorrencia.equipamento_id == equipamento_id, modelos.Ocorrencia.nivel == "leitura",
            modelos.Ocorrencia.severidade == "suspeita", modelos.Ocorrencia.resolvida_em.is_(None),
            modelos.Ocorrencia.tempo.isnot(None))
        if inicio is not None:
            consulta = consulta.where(modelos.Ocorrencia.tempo >= inicio)
        if fim is not None:
            consulta = consulta.where(modelos.Ocorrencia.tempo <= fim)
        return set(sessao.scalars(consulta))


# ---------------------------------------------------------------- leituras (generico)

def resumo_leituras(usuario: Usuario, equipamento_id: int, inicio: Optional[datetime] = None,
                    fim: Optional[datetime] = None) -> ResumoLeituras:
    """Leitura+. Quantas leituras (validas/corrompidas) o equipamento tem em
    [inicio, fim] e o periodo coberto, pela tabela do plugin do tipo dele.
    Equipamento de um tipo sem plugin carregado: tudo zero."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        equipamento = obter_equipamento_orm(sessao, equipamento_id)
        plugin = plugins.talvez(equipamento.tipo_sensor)
        if plugin is None:
            # sem o plugin: o que os envios registraram
            novas, primeira, ultima = sessao.execute(
                select(func.coalesce(func.sum(modelos.Envio.novas), 0), func.min(modelos.Envio.inicio),
                       func.max(modelos.Envio.fim)).where(modelos.Envio.equipamento_id == equipamento_id)).one()
            return ResumoLeituras(equipamento_id, novas, novas, 0, primeira, ultima)
        ing = plugin.ingestao
        tabela = ing.tabela
        tempo = getattr(tabela, ing.coluna_tempo)
        filtros = [tabela.equipamento_id == equipamento_id]
        if inicio is not None:
            filtros.append(tempo >= inicio)
        if fim is not None:
            filtros.append(tempo <= fim)
        corrompidas = (func.coalesce(func.sum(cast(getattr(tabela, ing.coluna_corrompido), Integer)), 0)
                       if ing.coluna_corrompido else 0)
        total, n_corrompidas, primeira, ultima = sessao.execute(
            select(func.count(), corrompidas, func.min(tempo), func.max(tempo)).select_from(tabela).where(*filtros)
        ).one()
        return ResumoLeituras(equipamento_id, total, total - n_corrompidas, n_corrompidas, primeira, ultima)


# ---------------------------------------------------------------- exportacao

def _qualidade_por_tempo(sessao: Session, equipamento_id: int):
    """qualidade(tempo) -> codigos das regras que marcaram a leitura
    (separados por ";"; vazio = nenhuma), para a coluna de qualidade."""
    marcas: dict = {}
    for tempo, codigo in sessao.execute(select(modelos.Ocorrencia.tempo, modelos.Ocorrencia.codigo_regra).where(
            modelos.Ocorrencia.equipamento_id == equipamento_id, modelos.Ocorrencia.nivel == "leitura",
            modelos.Ocorrencia.tempo.isnot(None))):
        marcas.setdefault(tempo, set()).add(codigo)
    textos = {t: ";".join(sorted(c)) for t, c in marcas.items()}
    return lambda tempo: textos.get(tempo, "")


FORMATO_GENERICO = FormatoExportacao("generico", "CSV genérico (todas as colunas da tabela do sensor)", ".csv",
                                     "text/csv")
_TABELAS_NUCLEO = {"usuario", "tipo_sensor", "equipamento", "envio", "plugin_instalado", "auditoria_plugin",
                   "regra_config", "ocorrencia", "alembic_version"}


def listar_formatos_exportacao(equipamento_id: int) -> list[FormatoExportacao]:
    """Formatos que o plugin do tipo do equipamento exporta. Sem o plugin
    carregado (ausente ou desativado): a exportacao generica em CSV."""
    with banco().sessao() as sessao:
        equipamento = obter_equipamento_orm(sessao, equipamento_id)
    plugin = plugins.talvez(equipamento.tipo_sensor)
    if plugin is None:
        return [FORMATO_GENERICO]
    return plugin.formatos_exportacao()


def _exportar_generico(sessao: Session, equipamento_id: int, inicio, fim, destino: Path) -> ResultadoExportacao:
    """CSV com todas as colunas (menos as binarias) das tabelas de leituras do
    equipamento, achadas no banco (colunas equipamento_id e envio_id), sem
    precisar do plugin. Para quando o plugin do tipo esta ausente."""
    import csv

    from sqlalchemy import MetaData, Table, inspect as inspecionar
    from sqlalchemy.types import LargeBinary

    resultado = ResultadoExportacao()
    conexao = sessao.connection()
    nomes = [t for t in inspecionar(conexao).get_table_names() if t not in _TABELAS_NUCLEO]
    with open(destino, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        cabecalho_escrito = False
        for nome in sorted(nomes):
            tabela = Table(nome, MetaData(), autoload_with=conexao)
            colunas = {c.name for c in tabela.columns}
            if not {"equipamento_id", "envio_id"} <= colunas:
                continue
            visiveis = [c for c in tabela.columns if not isinstance(c.type, LargeBinary)
                        and c.name not in ("equipamento_id",)]
            consulta = select(*visiveis).where(tabela.c.equipamento_id == equipamento_id)
            tempo = tabela.c.get("tempo")
            if tempo is not None:
                if inicio is not None:
                    consulta = consulta.where(tempo >= inicio)
                if fim is not None:
                    consulta = consulta.where(tempo <= fim)
                consulta = consulta.order_by(tempo)
            linhas = conexao.execute(consulta)
            for linha in linhas:
                if not cabecalho_escrito:
                    escritor.writerow(["tabela"] + [c.name for c in visiveis])
                    cabecalho_escrito = True
                escritor.writerow([nome] + ["" if v is None else (v.isoformat() if hasattr(v, "isoformat") else v)
                                            for v in linha])
                resultado.leituras += 1
                if tempo is not None:
                    t = linha._mapping["tempo"]
                    resultado.inicio = resultado.inicio or t
                    resultado.fim = t
        if not cabecalho_escrito:
            escritor.writerow(["tabela"])
    return resultado


def _nome_arquivo(equipamento: modelos.Equipamento, inicio, fim, extensao: str) -> str:
    nome = re.sub(r"[^A-Za-z0-9_-]+", "_", equipamento.nome).strip("_") or f"equipamento_{equipamento.id}"
    periodo = "_".join(d.strftime("%Y%m%d%H%M") for d in (inicio, fim) if d is not None)
    return f"{nome}_{periodo}{extensao}" if periodo else f"{nome}{extensao}"


def exportar(usuario: Usuario, equipamento_id: int, inicio: Optional[datetime], fim: Optional[datetime],
             formato: str, caminho_destino: Union[str, Path]) -> ResumoExportacao:
    """Leitura+. Exporta as leituras do equipamento em [inicio, fim] (None =
    sem limite) no formato pedido (codigo de listar_formatos_exportacao).
    caminho_destino: arquivo, ou uma pasta existente (o nome e gerado). O
    arquivo e escrito ao lado com nome temporario e so trocado no fim, entao
    um erro no meio nao deixa arquivo pela metade."""
    with sessao_autorizada(usuario, "leitura") as (sessao, _):
        equipamento = obter_equipamento_orm(sessao, equipamento_id)
        plugin = plugins.talvez(equipamento.tipo_sensor)
        formatos = ({f.codigo: f for f in plugin.formatos_exportacao()} if plugin is not None
                    else {FORMATO_GENERICO.codigo: FORMATO_GENERICO})
        contexto = ContextoExportacao(equipamento=_equipamento(equipamento),
                                      qualidade=_qualidade_por_tempo(sessao, equipamento_id),
                                      instituicao=instituicao_da_instalacao(configuracao().diretorio_dados))
        if formato not in formatos:
            raise ErroServico(f"formato '{formato}' nao disponivel para {equipamento.tipo_sensor} "
                              f"(use {', '.join(formatos) or 'nenhum'})")
        destino = Path(caminho_destino).expanduser()
        if destino.is_dir():
            destino = destino / _nome_arquivo(equipamento, inicio, fim, formatos[formato].extensao)
        if not destino.parent.is_dir():
            raise ErroServico(f"pasta de destino nao existe: {destino.parent}")
        temporario = destino.with_name(f".{destino.name}.parcial")
        try:
            if plugin is None:
                resultado = _exportar_generico(sessao, equipamento_id, inicio, fim, temporario)
            else:
                resultado = plugin.exportacao.exportar(sessao, equipamento_id, inicio, fim, formato, temporario,
                                                       contexto)
            os.replace(temporario, destino)
        finally:
            if temporario.exists():
                temporario.unlink()
    return ResumoExportacao(caminho=str(destino), formato=formato, equipamento_id=equipamento_id,
                            leituras=resultado.leituras, inicio=resultado.inicio, fim=resultado.fim,
                            tamanho_bytes=destino.stat().st_size)
