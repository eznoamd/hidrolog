"""Gerenciador de plugins: importar (pasta, .zip, GitHub), atualizar,
desativar, reativar e voltar versao. So o master, com a senha conferida de
novo aqui a cada acao (3 senhas erradas cancelam a operacao), e tudo vai
para a auditoria (auditoria_plugin).

Fluxo de importacao:
1. preparar(): copia/baixa o pacote para uma pasta temporaria, SEM executar
   nada do plugin: le o manifesto (hidrolog-plugin.toml, texto), calcula o
   SHA-256, confere contrato, codigo, dependencias (`requer`) e limites
   (tamanho, numero de arquivos, caminhos perigosos, links simbolicos);
2. instalar(): com a senha do master, copia de forma atomica para
   <dados do app>/plugins/<codigo>/<versao>/, marca a versao como ativa em
   plugins.json e registra em plugin_instalado e na auditoria;
3. o plugin so e carregado na proxima abertura do app ("reinicie para
   ativar"); as migracoes dele rodam entao, com backup do banco antes.

A versao anterior fica guardada na pasta (voltar versao). Remover ou
desativar um plugin nunca apaga dados.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from hidrolog_nucleo.plugin import NOME_MANIFESTO, ErroManifesto, contrato_compativel, ler_manifesto

from . import plugins
from .erros import ErroPermissao, ErroServico, NaoEncontrado
from .extracao import normalizar_caminho
from .modelos import AuditoriaPlugin, PluginInstalado

MAX_BYTES_PACOTE = 64 * 1024 * 1024        # descompactado
MAX_BYTES_DOWNLOAD = 32 * 1024 * 1024
MAX_ARQUIVOS_PACOTE = 5000
TENTATIVAS_SENHA = 3
IGNORAR = {"__pycache__", ".git", ".hg", ".svn", ".pytest_cache", ".mypy_cache", "venv", ".venv"}
_URL_GITHUB = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
_TAG_VALIDA = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/+-]{0,99}$")

Baixar = Callable[[str], bytes]


class SenhaIncorreta(ErroPermissao):
    """Senha do master errada numa acao do gerenciador. `restantes`: tentativas."""

    def __init__(self, mensagem: str, restantes: int):
        super().__init__(mensagem)
        self.restantes = restantes


class OperacaoCancelada(ErroPermissao):
    """Tres senhas erradas: a operacao foi cancelada (e auditada)."""
    encerrar = True     # a interface fecha o dialogo da senha


@dataclass
class PacotePreparado:
    """Um plugin pronto para instalar (ainda nao instalado). `token` identifica a preparacao."""

    token: str
    codigo: str
    nome: str
    versao: str
    contrato: str
    autor: str
    descricao: str
    modulo: str
    origem: str                 # pasta, zip ou github
    url: str = ""
    tag: str = ""
    sha256: str = ""
    arquivos: int = 0
    tamanho_bytes: int = 0
    tabelas: list[str] = field(default_factory=list)
    cadastro: list[str] = field(default_factory=list)
    requer: list[str] = field(default_factory=list)
    atualizacao: bool = False
    versao_atual: str = ""
    avisos: list[str] = field(default_factory=list)
    caminho_origem: str = ""

    @property
    def origem_legivel(self) -> str:
        if self.origem == "github":
            return f"{self.url.removeprefix('https://')} @ {self.tag}"
        return self.caminho_origem or self.origem


_preparados: dict[str, tuple[PacotePreparado, Path, tempfile.TemporaryDirectory, int]] = {}
_tentativas: dict[tuple, int] = {}


# ============================================================================ auditoria

def auditar(sessao: Session, usuario, acao: str, resultado: str, codigo: Optional[str] = None,
            versao: Optional[str] = None, origem: Optional[str] = None, detalhes: Optional[str] = None) -> None:
    sessao.add(AuditoriaPlugin(quando=datetime.now(), usuario_id=getattr(usuario, "id", None),
                               login=getattr(usuario, "login", None) or "sistema", acao=acao, codigo=codigo,
                               versao=versao, origem=origem, resultado=resultado, detalhes=detalhes))


def conferir_senha(banco, usuario, senha: str, chave: tuple, acao: str, codigo: Optional[str] = None,
                   versao: Optional[str] = None, ao_cancelar: Optional[Callable[[], None]] = None) -> None:
    """Confere de novo a senha do master logado (mesmo com a sessao aberta).
    Senha errada: SenhaIncorreta (auditada); na 3a, OperacaoCancelada."""
    from ..servico import autenticar
    from .erros import ErroAutenticacao

    try:
        atual = autenticar(usuario.login, senha or "")
        ok = atual.perfil == "master" and atual.id == usuario.id
    except ErroAutenticacao:
        ok = False
    if ok:
        _tentativas.pop(chave, None)
        return
    n = _tentativas.get(chave, 0) + 1
    with banco.sessao() as sessao:
        if n >= TENTATIVAS_SENHA:
            _tentativas.pop(chave, None)
            auditar(sessao, usuario, acao, "cancelado", codigo, versao,
                    detalhes=f"{TENTATIVAS_SENHA} senhas erradas: operacao cancelada")
        else:
            _tentativas[chave] = n
            auditar(sessao, usuario, acao, "recusado", codigo, versao,
                    detalhes=f"senha incorreta ({n} de {TENTATIVAS_SENHA})")
    if n >= TENTATIVAS_SENHA:
        if ao_cancelar is not None:
            ao_cancelar()
        raise OperacaoCancelada(f"{TENTATIVAS_SENHA} senhas erradas: a operacao foi cancelada")
    raise SenhaIncorreta(f"senha incorreta ({TENTATIVAS_SENHA - n} tentativa(s) restante(s))",
                         TENTATIVAS_SENHA - n)


# ============================================================================ preparacao (sem executar codigo)

def _copiar_pasta(origem: Path, destino: Path) -> int:
    """Copia a pasta do plugin (sem __pycache__, .git, venv), recusando links
    simbolicos e pacotes grandes demais. Devolve os bytes copiados."""
    total, n = 0, 0
    for raiz, pastas, arquivos in os.walk(origem):
        pastas[:] = sorted(p for p in pastas if p not in IGNORAR and not p.endswith(".egg-info"))
        for p in pastas:
            if (Path(raiz) / p).is_symlink():
                raise ErroServico(f"o pacote tem um link simbolico ({Path(raiz, p).relative_to(origem)}): recusado")
        for nome in sorted(arquivos):
            local = Path(raiz) / nome
            if local.is_symlink():
                raise ErroServico(f"o pacote tem um link simbolico ({local.relative_to(origem)}): recusado")
            if nome.endswith((".pyc", ".pyo")):
                continue
            n += 1
            total += local.stat().st_size
            if n > MAX_ARQUIVOS_PACOTE:
                raise ErroServico(f"o pacote passa de {MAX_ARQUIVOS_PACOTE} arquivos")
            if total > MAX_BYTES_PACOTE:
                raise ErroServico(f"o pacote passa de {MAX_BYTES_PACOTE // (1024 * 1024)} MB")
            alvo = destino / local.relative_to(origem)
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local, alvo)
    return total


def _extrair_zip(dados: bytes, destino: Path) -> int:
    """Extrai o zip do pacote com as protecoes da extracao de dados: sem path
    traversal, sem links, com limite de tamanho real e de numero de arquivos."""
    try:
        arquivo = zipfile.ZipFile(io.BytesIO(dados))
    except zipfile.BadZipFile as erro:
        raise ErroServico(f"o arquivo nao e um .zip valido ({erro})") from erro
    total, n = 0, 0
    with arquivo:
        for info in arquivo.infolist():
            caminho = normalizar_caminho(info.filename)
            if info.is_dir() or not caminho:
                continue
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ErroServico(f"o pacote tem um link simbolico ({caminho}): recusado")
            partes = caminho.split("/")
            if any(p in IGNORAR for p in partes) or caminho.endswith((".pyc", ".pyo")):
                continue
            n += 1
            if n > MAX_ARQUIVOS_PACOTE:
                raise ErroServico(f"o pacote passa de {MAX_ARQUIVOS_PACOTE} arquivos")
            alvo = destino / caminho
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with arquivo.open(info) as entrada, open(alvo, "wb") as saida:
                while True:
                    bloco = entrada.read(1024 * 1024)
                    if not bloco:
                        break
                    total += len(bloco)
                    if total > MAX_BYTES_PACOTE:
                        raise ErroServico(f"o pacote passa de {MAX_BYTES_PACOTE // (1024 * 1024)} MB descompactado")
                    saida.write(bloco)
    return total


def _raiz_do_pacote(pasta: Path) -> Path:
    """A pasta com o hidrolog-plugin.toml: a raiz, ou a unica pasta dentro
    dela (como no zip de uma tag do GitHub: <repo>-<tag>/...)."""
    if (pasta / NOME_MANIFESTO).is_file():
        return pasta
    filhas = [p for p in pasta.iterdir() if p.is_dir()]
    if len(filhas) == 1 and (filhas[0] / NOME_MANIFESTO).is_file():
        return filhas[0]
    raise ErroServico(f"o pacote nao tem o manifesto {NOME_MANIFESTO} na raiz")


def _hash_pasta(pasta: Path) -> str:
    h = hashlib.sha256()
    for arquivo in sorted(p for p in pasta.rglob("*") if p.is_file()):
        h.update(arquivo.relative_to(pasta).as_posix().encode() + b"\0")
        h.update(arquivo.read_bytes())
    return h.hexdigest()


def _revisoes(pasta: Path) -> set[str]:
    """Revisoes Alembic das migracoes do pacote, lidas como texto."""
    saida = set()
    for arquivo in pasta.rglob("*.py"):
        if "migracoes" not in arquivo.parts:
            continue
        m = re.search(r"^revision\s*(?::\s*str\s*)?=\s*['\"]([^'\"]+)['\"]", arquivo.read_text("utf-8", "replace"),
                      re.MULTILINE)
        if m:
            saida.add(m.group(1))
    return saida


def _tabelas(pasta: Path) -> list[str]:
    nomes = set()
    for arquivo in pasta.rglob("*.py"):
        if "migracoes" in arquivo.parts:
            nomes.update(re.findall(r"create_table\(\s*['\"]([A-Za-z0-9_]+)['\"]", arquivo.read_text("utf-8", "replace")))
    return sorted(nomes)


def baixar_padrao(url: str) -> bytes:
    """Baixa o zip de uma tag do GitHub (com limite de tamanho)."""
    requisicao = urllib.request.Request(url, headers={"User-Agent": "Hidrolog"})
    try:
        with urllib.request.urlopen(requisicao, timeout=60) as resposta:   # noqa: S310 - https do GitHub
            dados = resposta.read(MAX_BYTES_DOWNLOAD + 1)
    except OSError as erro:
        raise ErroServico(f"nao foi possivel baixar {url} ({erro})") from erro
    if len(dados) > MAX_BYTES_DOWNLOAD:
        raise ErroServico(f"o pacote passa de {MAX_BYTES_DOWNLOAD // (1024 * 1024)} MB")
    return dados


def url_da_tag(url_repositorio: str, tag: str, base: str = "https://github.com") -> tuple[str, str]:
    """(URL normalizada do repositorio, URL do zip da tag)."""
    m = _URL_GITHUB.match((url_repositorio or "").strip())
    if not m:
        raise ErroServico("use a URL de um repositorio do GitHub, ex. https://github.com/laboratorio/plugin-pluvio")
    tag = (tag or "").strip()
    if not tag or not _TAG_VALIDA.match(tag) or ".." in tag:
        raise ErroServico("informe a versao (tag ou release) do repositorio, ex. v0.1.0")
    dono, repo = m.group(1), m.group(2)
    return (f"https://github.com/{dono}/{repo}",
            f"{base.rstrip('/')}/{dono}/{repo}/archive/refs/tags/{urllib.parse.quote(tag, safe='')}.zip")


def preparar(origem: str, caminho: Optional[str] = None, url: Optional[str] = None, tag: Optional[str] = None,
             baixar: Optional[Baixar] = None, base_github: str = "https://github.com",
             usuario_id: int = 0) -> PacotePreparado:
    """Prepara um plugin para instalar (sem executar nada dele). origem:
    "pasta" (caminho), "zip" (caminho) ou "github" (url + tag)."""
    temp = tempfile.TemporaryDirectory(prefix="hidrolog_plugin_")
    pasta = Path(temp.name) / "pacote"
    pasta.mkdir()
    try:
        url_repo = ""
        if origem == "pasta":
            local = Path(caminho or "").expanduser()
            if not local.is_dir():
                raise ErroServico(f"pasta nao encontrada: {local}")
            tamanho = _copiar_pasta(local, pasta)
            raiz = _raiz_do_pacote(pasta)
            sha = _hash_pasta(raiz)
        elif origem in ("zip", "github"):
            if origem == "zip":
                local = Path(caminho or "").expanduser()
                if not local.is_file():
                    raise ErroServico(f"arquivo nao encontrado: {local}")
                if local.stat().st_size > MAX_BYTES_DOWNLOAD:
                    raise ErroServico(f"o pacote passa de {MAX_BYTES_DOWNLOAD // (1024 * 1024)} MB")
                dados = local.read_bytes()
            else:
                url_repo, url_zip = url_da_tag(url, tag, base_github)
                confiaveis = [c.rstrip("/").lower() for c in plugins.ler_estado(plugins.diretorio())
                              .get("github_confiaveis", [])]
                if confiaveis and not any(url_repo.lower() == c or url_repo.lower().startswith(c + "/")
                                          for c in confiaveis):
                    raise ErroServico(f"{url_repo} nao esta na lista de repositorios confiaveis do app")
                dados = (baixar or baixar_padrao)(url_zip)
            sha = hashlib.sha256(dados).hexdigest()
            tamanho = _extrair_zip(dados, pasta)
            raiz = _raiz_do_pacote(pasta)
        else:
            raise ErroServico(f"origem desconhecida: {origem!r} (use pasta, zip ou github)")
        try:
            manifesto = ler_manifesto(raiz)
        except ErroManifesto as erro:
            raise ErroServico(f"manifesto invalido: {erro}") from erro
        pacote = PacotePreparado(
            token=uuid.uuid4().hex, codigo=manifesto.codigo, nome=manifesto.nome, versao=manifesto.versao,
            contrato=manifesto.contrato, autor=manifesto.autor, descricao=manifesto.descricao,
            modulo=manifesto.modulo, origem=origem, url=url_repo, tag=(tag or "").strip() if url_repo else "",
            sha256=sha, arquivos=sum(1 for p in raiz.rglob("*") if p.is_file()), tamanho_bytes=tamanho,
            tabelas=list(manifesto.tabelas) or _tabelas(raiz), cadastro=list(manifesto.cadastro),
            requer=list(manifesto.requer), caminho_origem=str(caminho or ""))
        _validar(pacote, raiz)
    except BaseException:
        temp.cleanup()
        raise
    _preparados[pacote.token] = (pacote, raiz, temp, usuario_id)
    return pacote


def _validar(pacote: PacotePreparado, raiz: Path) -> None:
    if not contrato_compativel(pacote.contrato):
        raise ErroServico(f"o plugin usa o contrato {pacote.contrato}, incompativel com o do app "
                          f"({plugins.VERSAO_CONTRATO.split('.')[0]}.x)")
    topo = pacote.modulo.split(".")[0]
    if not (raiz / topo / "__init__.py").is_file():
        raise ErroServico(f"o pacote nao tem o modulo {topo}/ (declarado em 'modulo' no manifesto)")
    faltando = [r for r in pacote.requer if importlib.util.find_spec(r.split("[")[0].strip()) is None]
    if faltando:
        raise ErroServico("o app nao tem as dependencias que o plugin exige: " + ", ".join(faltando)
                          + ". Dependencias em Python puro podem vir junto no pacote do plugin.")
    estado = plugins.ler_estado(plugins.diretorio())
    atual = estado["plugins"].get(pacote.codigo, {})
    carregado = plugins.talvez(pacote.codigo)
    situacoes = {s.codigo: s for s in plugins.situacoes() if s.estado != "conflito"}
    if atual.get("versao"):
        pacote.atualizacao = True
        pacote.versao_atual = atual["versao"]
        instaladas = versoes_guardadas(pacote.codigo)
        if pacote.versao in instaladas:
            raise ErroServico(f"a versao {pacote.versao} de {pacote.nome} ja esta instalada; "
                              "use voltar versao para ativa-la")
    elif carregado is not None or pacote.codigo in situacoes:
        modulo_existente = carregado.manifesto.modulo if carregado else ""
        if modulo_existente and modulo_existente.split(".")[0] != pacote.modulo.split(".")[0]:
            raise ErroServico(f"o codigo {pacote.codigo!r} ja pertence a outro plugin "
                              f"({situacoes[pacote.codigo].nome}, modulo {modulo_existente})")
        pacote.atualizacao = True
        pacote.versao_atual = situacoes[pacote.codigo].versao if pacote.codigo in situacoes else ""
        if situacoes.get(pacote.codigo) and situacoes[pacote.codigo].origem == "interno":
            pacote.avisos.append("este plugin tambem esta instalado no ambiente de desenvolvimento (entry point); "
                                 "enquanto estiver la, a versao de desenvolvimento e a que vale")
    if pacote.atualizacao and pacote.versao_atual == pacote.versao:
        raise ErroServico(f"a versao {pacote.versao} de {pacote.nome} ja esta instalada")


def obter_preparado(token: str, usuario_id: int) -> tuple[PacotePreparado, Path]:
    item = _preparados.get(token)
    if item is None or item[3] != usuario_id:
        raise NaoEncontrado("a preparacao do plugin expirou; importe de novo")
    return item[0], item[1]


def descartar(token: str) -> None:
    item = _preparados.pop(token, None)
    if item is not None:
        item[2].cleanup()


# ============================================================================ instalacao e acoes

def versoes_guardadas(codigo: str) -> list[str]:
    pasta = plugins.diretorio()
    if pasta is None or not (pasta / codigo).is_dir():
        return []
    return sorted((p.name for p in (pasta / codigo).iterdir() if p.is_dir() and not p.name.startswith(".")),
                  key=_chave_versao)


def _chave_versao(v: str):
    return tuple(int(x) if x.isdigit() else x for x in re.split(r"[.\-+]", v))


def instalar(sessao: Session, usuario, pacote: PacotePreparado, raiz: Path) -> Path:
    """Copia o pacote preparado para a pasta de plugins (atomico) e o marca como ativo."""
    base = plugins.diretorio()
    if base is None:
        raise ErroServico("o app nao tem pasta de plugins configurada")
    destino = base / pacote.codigo / pacote.versao
    if destino.exists():
        raise ErroServico(f"a versao {pacote.versao} de {pacote.nome} ja esta instalada")
    temporario = base / pacote.codigo / f".{pacote.versao}.tmp-{pacote.token}"
    temporario.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(raiz, temporario)
        os.replace(temporario, destino)
    finally:
        if temporario.exists():
            shutil.rmtree(temporario, ignore_errors=True)
    estado = plugins.ler_estado(base)
    estado["plugins"][pacote.codigo] = {"versao": pacote.versao, "ativo": True, "origem": pacote.origem,
                                        "url": pacote.url, "tag": pacote.tag, "sha256": pacote.sha256}
    plugins.gravar_estado(base, estado)
    for anterior in sessao.scalars(select(PluginInstalado).where(PluginInstalado.codigo == pacote.codigo)):
        if anterior.situacao == "ativo":
            anterior.situacao = "guardada"
    sessao.add(PluginInstalado(codigo=pacote.codigo, nome=pacote.nome, versao=pacote.versao,
                               contrato=pacote.contrato, origem=pacote.origem, url=pacote.url or None,
                               tag=pacote.tag or None, sha256=pacote.sha256, caminho=str(destino),
                               instalado_por=usuario.id, instalado_em=datetime.now(), situacao="ativo"))
    return destino


def definir_ativo(sessao: Session, codigo: str, ativo: bool) -> None:
    """Desativa/reativa (plugin da pasta ou interno). Os dados ficam no banco."""
    base = plugins.diretorio()
    if base is None:
        raise ErroServico("o app nao tem pasta de plugins configurada")
    estado = plugins.ler_estado(base)
    registro = estado["plugins"].setdefault(codigo, {})
    registro["ativo"] = bool(ativo)
    plugins.gravar_estado(base, estado)
    for linha in sessao.scalars(select(PluginInstalado).where(PluginInstalado.codigo == codigo)):
        if ativo and linha.situacao == "desativado":
            linha.situacao = "ativo" if (not registro.get("versao") or linha.versao == registro["versao"]) \
                else "guardada"
        elif not ativo and linha.situacao == "ativo":
            linha.situacao = "desativado"


def trocar_versao(sessao: Session, codigo: str, versao: str, revisoes_aplicadas: set[str]) -> None:
    """Ativa uma versao guardada. Recusa se a versao atual ja aplicou
    migracoes que a outra nao conhece (seria preciso desfazer o banco)."""
    base = plugins.diretorio()
    estado = plugins.ler_estado(base)
    atual = estado["plugins"].get(codigo, {})
    if versao not in versoes_guardadas(codigo):
        raise NaoEncontrado(f"a versao {versao} de {codigo} nao esta guardada")
    if atual.get("versao") == versao:
        raise ErroServico(f"a versao {versao} ja e a ativa")
    novas = set()
    if atual.get("versao"):
        novas = _revisoes(base / codigo / atual["versao"]) - _revisoes(base / codigo / versao)
    aplicadas = sorted(novas & revisoes_aplicadas)
    if aplicadas:
        raise ErroServico(
            f"a versao {atual['versao']} ja aplicou no banco migracoes que a {versao} nao conhece "
            f"({', '.join(aplicadas)}). Para voltar, restaure o backup do banco feito antes dessas migracoes "
            "(arquivo hidrolog.backup-... na pasta de dados do app).")
    registro = dict(atual, versao=versao, ativo=True)
    linha = sessao.scalar(select(PluginInstalado).where(PluginInstalado.codigo == codigo,
                                                        PluginInstalado.versao == versao))
    if linha is not None:
        registro.update(origem=linha.origem, url=linha.url or "", tag=linha.tag or "", sha256=linha.sha256 or "")
    estado["plugins"][codigo] = registro
    plugins.gravar_estado(base, estado)
    for l in sessao.scalars(select(PluginInstalado).where(PluginInstalado.codigo == codigo)):
        l.situacao = "ativo" if l.versao == versao else ("guardada" if l.situacao in ("ativo", "desativado")
                                                          else l.situacao)


def definir_confiaveis(lista: list[str]) -> list[str]:
    base = plugins.diretorio()
    if base is None:
        raise ErroServico("o app nao tem pasta de plugins configurada")
    limpas = []
    for item in lista:
        item = item.strip().rstrip("/")
        if not item:
            continue
        if not item.startswith("https://github.com/"):
            item = "https://github.com/" + item.removeprefix("github.com/").lstrip("/")
        limpas.append(item)
    estado = plugins.ler_estado(base)
    estado["github_confiaveis"] = limpas
    plugins.gravar_estado(base, estado)
    return limpas


def sincronizar(sessao: Session, usuario_sistema=None) -> None:
    """plugin_instalado reflete o que foi visto na carga: uma linha por
    (codigo, versao); os internos (entry point) tambem aparecem."""
    vistos = {s.codigo: s for s in plugins.situacoes() if s.estado != "conflito"}
    linhas = {(l.codigo, l.versao): l for l in sessao.scalars(select(PluginInstalado))}
    for codigo, s in vistos.items():
        linha = linhas.get((codigo, s.versao))
        situacao = {"ativo": "ativo", "desativado": "desativado"}.get(s.estado, s.estado)
        if linha is None:
            if s.versao == "?":
                continue
            sessao.add(PluginInstalado(codigo=codigo, nome=s.nome, versao=s.versao, contrato=s.contrato,
                                       origem=s.origem, url=s.url or None, tag=s.tag or None, caminho=s.caminho,
                                       instalado_em=datetime.now(), situacao=situacao, motivo=s.motivo or None))
        else:
            linha.situacao = situacao
            linha.motivo = s.motivo or None
            linha.nome = s.nome
