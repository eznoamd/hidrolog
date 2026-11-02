"""Contrato v1 entre o nucleo do Hidrolog e os plugins de sensor.

Um plugin e um pacote Python que expoe um objeto PLUGIN (uma instancia de
Plugin) e traz, ao lado do pacote, o manifesto `hidrolog-plugin.toml`. O
nucleo descobre os plugins por entry points (grupo "hidrolog.plugins") e
pela pasta de plugins do app; ver app/nucleo/plugins.py.

    PLUGIN = Plugin(
        manifesto = carregar_manifesto(__file__),
        modelos = (MinhaLeitura,), migracoes = Path(__file__).parent / "migracoes",
        ingestao = Ingestao(tabela=MinhaLeitura, reconhecer=reconhecer, ler=ler),
        ficha = FICHA, regras = REGRAS,
        consultas = "meu_plugin.consultas",           # modulo, importado sob demanda
        interface = "meu_plugin.interface",           # modulo com ABAS (so ele importa PySide6)
    )

Este modulo nao importa Qt nem o codigo do servico na carga: o backend, o
comando de linha e os testes sem tela importam o plugin sem a interface.

Ingestao em tres camadas:

    1. nucleo  ABRIR       zip / rar / pasta / arquivos soltos (+ zip dentro de zip,
                           ate 2 niveis) -> ArvoreArquivos (nomes e tamanhos, sem ler)
    2. plugin  RECONHECER  reconhecer(arvore, verificar=False) -> PlanoImportacao | Recusa
    3. plugin  LER         ler(unidade) -> gerador de dicts (uma leitura por dict)
       nucleo  GRAVAR      lotes numa transacao, deduplicacao pela chave, progresso,
                           cancelamento, paralelismo, regras de qualidade, registro do envio
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterable, Iterator, Optional, Sequence, Union

from app.nucleo.erros import ErroServico, ErroValidacao
from app.nucleo.modelos import Base
from app.nucleo.tipos import (
    Equipamento,
    FormatoExportacao,
    ResultadoExportacao,
    Usuario,
)

VERSAO_CONTRATO = "1.0"
NOME_MANIFESTO = "hidrolog-plugin.toml"
GRUPO_ENTRY_POINTS = "hidrolog.plugins"

__all__ = [
    "VERSAO_CONTRATO", "NOME_MANIFESTO", "GRUPO_ENTRY_POINTS",
    "Plugin", "Manifesto", "carregar_manifesto", "ler_manifesto", "contrato_compativel",
    "Campo", "Regra", "Ocorrencia", "ContextoRegra",
    "Aba", "ContextoAba",
    "ArquivoArvore", "ArquivoMemoria", "ArvoreArquivos", "PlanoImportacao", "Unidade", "Recusa", "Ingestao",
    "Exportacao", "ContextoExportacao",
    "Base", "Equipamento", "Usuario", "FormatoExportacao", "ResultadoExportacao", "ErroServico", "ErroValidacao",
    "sessao_autorizada", "obter_equipamento_orm", "usuario_da_api",
]


# ============================================================================ manifesto

_CODIGO_VALIDO = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_VERSAO_VALIDA = re.compile(r"^\d+\.\d+\.\d+([-+.][0-9A-Za-z.-]+)?$")
_CONTRATO_VALIDO = re.compile(r"^(\d+)\.(x|\d+)$")


class ErroManifesto(ValueError):
    """Manifesto ausente ou invalido (a mensagem diz o que corrigir)."""


@dataclass(frozen=True)
class Manifesto:
    """O que o plugin declara sobre si (hidrolog-plugin.toml).

    codigo:   identificador do tipo de sensor (minusculas, digitos e _), vai
              para tipo_sensor.codigo e para o branch Alembic do plugin;
    contrato: versao do contrato do nucleo que o plugin usa, ex. "1.x";
    modulo:   pacote Python que tem o objeto PLUGIN;
    requer:   dependencias compiladas (ou grandes) que o app precisa ter
              (numpy, netCDF4...); o instalador recusa o plugin se faltar uma."""

    codigo: str
    nome: str
    versao: str
    contrato: str
    modulo: str
    descricao: str = ""
    icone: str = "cpu"
    autor: str = ""
    requer: tuple[str, ...] = ()
    tabelas: tuple[str, ...] = ()       # so para mostrar na confirmacao da instalacao
    cadastro: tuple[str, ...] = ()      # idem: campos que o plugin acrescenta a ficha

    @classmethod
    def de_dict(cls, dados: dict) -> "Manifesto":
        faltando = [c for c in ("codigo", "nome", "versao", "contrato", "modulo") if not dados.get(c)]
        if faltando:
            raise ErroManifesto(f"faltam no manifesto: {', '.join(faltando)}")
        codigo = str(dados["codigo"])
        if not _CODIGO_VALIDO.match(codigo):
            raise ErroManifesto(f"codigo invalido {codigo!r}: use letras minusculas, digitos e _ (2 a 40)")
        versao = str(dados["versao"])
        if not _VERSAO_VALIDA.match(versao):
            raise ErroManifesto(f"versao invalida {versao!r}: use o formato 1.2.3")
        contrato = str(dados["contrato"])
        if not _CONTRATO_VALIDO.match(contrato):
            raise ErroManifesto(f"contrato invalido {contrato!r}: use o formato 1.x")
        modulo = str(dados["modulo"])
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$", modulo):
            raise ErroManifesto(f"modulo invalido {modulo!r}: use o nome de um pacote Python")

        def _tupla(chave):
            valor = dados.get(chave) or ()
            if isinstance(valor, str) or not isinstance(valor, (list, tuple)):
                raise ErroManifesto(f"{chave} precisa ser uma lista")
            return tuple(str(v) for v in valor)

        return cls(codigo=codigo, nome=str(dados["nome"]), versao=versao, contrato=contrato, modulo=modulo,
                   descricao=str(dados.get("descricao", "")), icone=str(dados.get("icone", "cpu")),
                   autor=str(dados.get("autor", "")), requer=_tupla("requer"), tabelas=_tupla("tabelas"),
                   cadastro=_tupla("cadastro"))


def ler_manifesto(caminho: Union[str, Path]) -> Manifesto:
    """Le um hidrolog-plugin.toml (arquivo de texto, sem executar codigo)."""
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    caminho = Path(caminho)
    if caminho.is_dir():
        caminho = caminho / NOME_MANIFESTO
    if not caminho.is_file():
        raise ErroManifesto(f"nao ha {NOME_MANIFESTO} em {caminho.parent}")
    try:
        dados = tomllib.loads(caminho.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as erro:
        raise ErroManifesto(f"{NOME_MANIFESTO} invalido: {erro}") from erro
    return Manifesto.de_dict(dados)


def carregar_manifesto(arquivo_do_pacote: Union[str, Path]) -> Manifesto:
    """Manifesto do plugin a partir do __file__ do pacote: procura o
    hidrolog-plugin.toml na pasta do pacote e nas duas acima."""
    pasta = Path(arquivo_do_pacote).resolve().parent
    for candidata in (pasta, pasta.parent, pasta.parent.parent):
        if (candidata / NOME_MANIFESTO).is_file():
            return ler_manifesto(candidata / NOME_MANIFESTO)
    raise ErroManifesto(f"nao ha {NOME_MANIFESTO} perto de {pasta}")


def contrato_compativel(declarado: str, nucleo: str = VERSAO_CONTRATO) -> bool:
    """"1.x" ou "1.0" servem para o nucleo 1.y (mesma versao maior; a menor
    declarada precisa ser <= a do nucleo)."""
    m = _CONTRATO_VALIDO.match(declarado or "")
    if not m:
        return False
    maior_n, menor_n = (int(p) for p in nucleo.split(".")[:2])
    if int(m.group(1)) != maior_n:
        return False
    return m.group(2) == "x" or int(m.group(2)) <= menor_n


# ============================================================================ ficha do equipamento

TIPOS_CAMPO = ("texto", "inteiro", "decimal", "booleano", "data", "escolha")


@dataclass(frozen=True)
class Campo:
    """Um campo da ficha do equipamento (cadastro especifico do tipo).

    tipo: texto | inteiro | decimal | booleano | data | escolha (com opcoes).
    origem="leituras": preenchido pelo nucleo a partir das leituras (o valor
    mais recente nao nulo da `coluna` da tabela do plugin); somente leitura."""

    chave: str
    rotulo: str
    tipo: str = "texto"
    unidade: Optional[str] = None
    obrigatorio: bool = False
    padrao: Any = None
    minimo: Optional[float] = None
    maximo: Optional[float] = None
    opcoes: tuple = ()                   # escolha: valores aceitos (ou pares (valor, rotulo))
    ajuda: str = ""
    somente_leitura: bool = False
    origem: Optional[str] = None         # None (digitado) ou "leituras"
    coluna: Optional[str] = None         # origem="leituras": coluna da tabela de leituras

    def __post_init__(self):
        if self.tipo not in TIPOS_CAMPO:
            raise ValueError(f"campo {self.chave}: tipo {self.tipo!r} invalido (use {', '.join(TIPOS_CAMPO)})")
        if self.origem not in (None, "leituras"):
            raise ValueError(f"campo {self.chave}: origem {self.origem!r} invalida")

    @property
    def editavel(self) -> bool:
        return not self.somente_leitura and self.origem is None

    def valores_opcoes(self) -> list:
        return [o[0] if isinstance(o, (tuple, list)) else o for o in self.opcoes]

    def validar(self, valor: Any) -> Any:
        """Valor normalizado (None = vazio), ou ValueError com a mensagem."""
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            if self.obrigatorio:
                raise ValueError("campo obrigatorio")
            return None
        if self.tipo == "texto":
            return str(valor).strip()
        if self.tipo == "booleano":
            if isinstance(valor, bool):
                return valor
            texto = str(valor).strip().lower()
            if texto in ("1", "sim", "true", "verdadeiro", "s"):
                return True
            if texto in ("0", "nao", "não", "false", "falso", "n"):
                return False
            raise ValueError("use sim ou nao")
        if self.tipo == "data":
            if isinstance(valor, datetime):
                return valor.date().isoformat()
            if isinstance(valor, date):
                return valor.isoformat()
            try:
                return date.fromisoformat(str(valor).strip()).isoformat()
            except ValueError:
                raise ValueError("data invalida (use AAAA-MM-DD)") from None
        if self.tipo == "escolha":
            if valor not in self.valores_opcoes():
                raise ValueError(f"valor fora das opcoes ({', '.join(map(str, self.valores_opcoes()))})")
            return valor
        # numericos
        if isinstance(valor, bool):
            raise ValueError("numero invalido")
        try:
            numero = float(str(valor).strip().replace(",", ".")) if isinstance(valor, str) else float(valor)
        except (TypeError, ValueError):
            raise ValueError("numero invalido") from None
        if numero != numero:   # NaN
            raise ValueError("numero invalido")
        if self.tipo == "inteiro":
            if numero != int(numero):
                raise ValueError("use um numero inteiro")
            numero = int(numero)
        if self.minimo is not None and numero < self.minimo:
            raise ValueError(f"minimo {_fmt(self.minimo)}" + (f" {self.unidade}" if self.unidade else ""))
        if self.maximo is not None and numero > self.maximo:
            raise ValueError(f"maximo {_fmt(self.maximo)}" + (f" {self.unidade}" if self.unidade else ""))
        return numero


def _fmt(n: float) -> str:
    return str(int(n)) if float(n) == int(n) else str(n)


def validar_ficha(ficha: Sequence[Campo], atributos: Optional[dict], anteriores: Optional[dict] = None) -> dict:
    """Valida os atributos contra a ficha. Campos desconhecidos sao recusados;
    campos nao editaveis mantem o valor anterior (o usuario nao os muda);
    campos ausentes recebem o padrao. Erro: ErroValidacao com {chave: mensagem}."""
    atributos = dict(atributos or {})
    anteriores = dict(anteriores or {})
    por_chave = {c.chave: c for c in ficha}
    erros: dict[str, str] = {}
    for chave in atributos:
        if chave not in por_chave:
            erros[chave] = "campo desconhecido para este tipo de sensor"
    saida: dict = {}
    for campo in ficha:
        if not campo.editavel:
            if anteriores.get(campo.chave) is not None:
                saida[campo.chave] = anteriores[campo.chave]
            continue
        valor = atributos.get(campo.chave, anteriores.get(campo.chave, campo.padrao))
        try:
            normalizado = campo.validar(valor)
        except ValueError as erro:
            erros[campo.chave] = str(erro)
            continue
        if normalizado is not None:
            saida[campo.chave] = normalizado
    if erros:
        rotulos = {c.chave: c.rotulo for c in ficha}
        raise ErroValidacao("ficha do equipamento com valores invalidos: "
                            + "; ".join(f"{rotulos.get(k, k)}: {v}" for k, v in erros.items()), campos=erros)
    return saida


# ============================================================================ regras de qualidade

NIVEIS_REGRA = ("leitura", "envio", "equipamento")
SEVERIDADES = ("aviso", "suspeita", "alerta")
_OPERADORES = {
    ">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b, "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
}


@dataclass(frozen=True)
class Ocorrencia:
    """O que uma regra encontrou. O nucleo completa codigo, nivel e equipamento."""

    mensagem: str
    tempo: Optional[datetime] = None          # leitura (nivel leitura) ou instante do problema
    severidade: Optional[str] = None          # None = a da regra


@dataclass
class ContextoRegra:
    """O que uma regra-funcao recebe.

    nivel "leitura": `linhas` sao as leituras novas de um lote (dicts com as
    colunas da tabela do plugin). Nivel "envio": `envio` e o ResumoEnvio e
    `inicio`/`fim` o periodo dele. Nivel "equipamento": `agora`.
    `sessao` e uma sessao SQLAlchemy so para consultas: regras NUNCA alteram dados."""

    equipamento: Equipamento
    parametros: dict
    sessao: Any = None
    linhas: list = field(default_factory=list)
    envio: Any = None
    inicio: Optional[datetime] = None
    fim: Optional[datetime] = None
    agora: Optional[datetime] = None

    @property
    def atributos(self) -> dict:
        return self.equipamento.atributos or {}


@dataclass(frozen=True)
class Regra:
    """Uma verificacao de qualidade. Duas formas:

    declarativa (so nivel "leitura"): `coluna`, `operador` (> >= < <= == !=) e
    `limite` (nome do parametro com o valor de comparacao, ou um numero);
    gera uma ocorrencia por leitura em que `coluna operador limite` e verdade.
    `mensagem` pode usar {valor} e os parametros, ex. "{valor:.0f} mm/h > {limite_mm_h}".

    por funcao: `funcao(contexto: ContextoRegra) -> list[Ocorrencia]`.

    Os parametros (com padrao) podem ser ajustados por equipamento (regra_config)."""

    codigo: str
    descricao: str
    nivel: str = "leitura"
    severidade: str = "aviso"
    parametros: dict = field(default_factory=dict)
    coluna: Optional[str] = None
    operador: Optional[str] = None
    limite: Union[str, float, None] = None
    mensagem: str = ""
    funcao: Optional[Callable[[ContextoRegra], list]] = None
    ajuda_parametros: dict = field(default_factory=dict)    # {parametro: "texto de ajuda (unidade)"}

    def __post_init__(self):
        if self.nivel not in NIVEIS_REGRA:
            raise ValueError(f"regra {self.codigo}: nivel {self.nivel!r} invalido")
        if self.severidade not in SEVERIDADES:
            raise ValueError(f"regra {self.codigo}: severidade {self.severidade!r} invalida")
        if self.funcao is None:
            if self.nivel != "leitura" or not self.coluna or self.operador not in _OPERADORES or self.limite is None:
                raise ValueError(f"regra {self.codigo}: declarativa precisa de nivel leitura, coluna, "
                                 "operador e limite; senao use funcao")

    @property
    def declarativa(self) -> bool:
        return self.funcao is None

    def avaliar(self, contexto: ContextoRegra, coluna_tempo: str = "tempo") -> list[Ocorrencia]:
        if self.funcao is not None:
            return list(self.funcao(contexto) or [])
        limite = contexto.parametros.get(self.limite) if isinstance(self.limite, str) else self.limite
        if limite is None:
            return []
        comparar = _OPERADORES[self.operador]
        saida = []
        for linha in contexto.linhas:
            valor = linha.get(self.coluna)
            if valor is None:
                continue
            try:
                disparou = comparar(valor, limite)
            except TypeError:
                continue
            if disparou:
                texto = (self.mensagem or f"{self.coluna} {{valor}} {self.operador} {{limite}}")
                try:
                    texto = texto.format(valor=valor, limite=limite, **contexto.parametros)
                except (KeyError, ValueError, IndexError):
                    pass
                saida.append(Ocorrencia(texto, linha.get(coluna_tempo)))
        return saida


# ============================================================================ interface

@dataclass(frozen=True)
class Aba:
    """Uma aba da pagina do equipamento. `fabrica(contexto: ContextoAba)`
    devolve o QWidget da aba. O widget pode ter `atualizar(contexto)`, chamado
    quando o periodo, o filtro de qualidade ou os dados mudam. Declare as abas
    no modulo de interface do plugin (so ele importa PySide6), numa lista ABAS."""

    chave: str
    titulo: str
    fabrica: Callable[["ContextoAba"], Any]
    icone: str = "layout-dashboard"
    descricao: str = ""                    # uma frase sob o titulo da aba
    perfis: Optional[frozenset] = None     # None = todos os perfis


@dataclass(frozen=True)
class ContextoAba:
    """O que cada aba recebe pronto: ela nao escolhe equipamento nem periodo.

    equipamento: o Equipamento (com atributos da ficha);
    inicio/fim:  periodo escolhido no cabecalho (datetime; None = sem limite);
    usuario:     o Usuario logado (para as consultas, que conferem o perfil);
    consultas:   o modulo de consultas do plugin (Plugin.consultas), ja importado;
    ocultar_suspeitas: filtro "ocultar suspeitas" do cabecalho;
    suspeitas:   funcao() -> set de tempos (datetime) das leituras suspeitas no periodo;
    executar:    executar(funcao, *args, ao_concluir=..., ao_falhar=...) numa thread;
    tratar_erro: tratar_erro(erro, contexto="") -> mensagem amigavel (e grava no log);
    sessao:      o contexto de sessao da interface (opaco; guarde estado em sessao.extras)."""

    equipamento: Equipamento
    usuario: Usuario
    inicio: Optional[datetime] = None
    fim: Optional[datetime] = None
    consultas: Any = None
    ocultar_suspeitas: bool = False
    suspeitas: Callable[[], set] = field(default=lambda: set())
    executar: Optional[Callable[..., Any]] = None
    tratar_erro: Optional[Callable[..., str]] = None
    sessao: Any = None
    versao_dados: int = 0                 # muda quando ha importacao nova (para caches)

    def chave(self) -> tuple:
        """Identifica o que a aba mostra (para caches)."""
        return (self.equipamento.id, self.inicio, self.fim, self.ocultar_suspeitas, self.versao_dados)

    def pode(self, perfil: str) -> bool:
        return self.usuario.pode(perfil)


# ============================================================================ ingestao

class ArquivoArvore:
    """Um arquivo do envio, sem o conteudo carregado. O conteudo so e lido quando
    o plugin pede (`ler`, `abrir`, `linhas`...), sempre com os limites do envio.

    caminho: relativo, com "/" (num zip dentro de zip: "externo.zip/dentro/arq.txt")."""

    def __init__(self, caminho: str, tamanho: Optional[int] = None):
        self.caminho = caminho
        self.tamanho = tamanho
        self._contador = None

    # o nucleo implementa a abertura de cada origem (zip, rar, pasta, upload)
    def _abrir_bruto(self) -> BinaryIO:
        raise NotImplementedError

    @property
    def nome(self) -> str:
        return self.caminho.rpartition("/")[2]

    @property
    def pasta(self) -> str:
        return self.caminho.rpartition("/")[0]

    @property
    def extensao(self) -> str:
        nome = self.nome
        ponto = nome.rfind(".")
        return nome[ponto:].lower() if ponto > 0 else ""

    def abrir(self) -> BinaryIO:
        """Fluxo binario do conteudo (para arquivos grandes). Conta para o limite do envio."""
        bruto = self._abrir_bruto()
        if self._contador is None:
            return bruto
        return self._contador.fluxo(bruto, self.caminho)

    def ler(self) -> bytes:
        """Conteudo inteiro (para arquivos pequenos: limite por arquivo do envio)."""
        if self._contador is None:
            with self._abrir_bruto() as f:
                return f.read()
        with self._abrir_bruto() as f:
            return self._contador.ler(f, self.caminho)

    def texto(self, codificacao: str = "utf-8") -> str:
        return self.ler().decode(codificacao, errors="replace")

    def linhas(self, codificacao: str = "utf-8") -> Iterator[str]:
        """Linhas de texto em fluxo (sem o fim de linha)."""
        with self.abrir() as f:
            for linha in io.TextIOWrapper(f, encoding=codificacao, errors="replace", newline=""):
                yield linha.rstrip("\r\n")

    def primeira_linha(self, codificacao: str = "utf-8") -> str:
        for linha in self.linhas(codificacao):
            return linha.lstrip("﻿")
        return ""

    def linhas_csv(self, separador: Optional[str] = None, codificacao: str = "utf-8") -> Iterator[dict]:
        """Linhas de um CSV com cabecalho, como dicts, em fluxo. Sem separador,
        usa ';' se o cabecalho tiver ';', senao ','."""
        if separador is None:
            separador = ";" if ";" in self.primeira_linha(codificacao) else ","
        primeira = True
        linhas = self.linhas(codificacao)

        def _sem_bom():
            nonlocal primeira
            for linha in linhas:
                if primeira:
                    linha = linha.lstrip("﻿")
                    primeira = False
                yield linha

        yield from csv.DictReader(_sem_bom(), delimiter=separador)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.caminho}>"


class ArquivoMemoria(ArquivoArvore):
    """Arquivo com o conteudo ja na memoria (usado nos processos de leitura em
    paralelo e nos testes)."""

    def __init__(self, caminho: str, conteudo: bytes):
        super().__init__(caminho, len(conteudo))
        self.conteudo = conteudo

    def _abrir_bruto(self) -> BinaryIO:
        return io.BytesIO(self.conteudo)

    def ler(self) -> bytes:
        return self.conteudo

    def __getstate__(self):
        return {"caminho": self.caminho, "tamanho": self.tamanho, "conteudo": self.conteudo, "_contador": None}


class ArvoreArquivos:
    """Todos os arquivos de um envio (de todas as origens juntas), sem conteudo."""

    def __init__(self, arquivos: Iterable[ArquivoArvore] = ()):
        self.arquivos: list[ArquivoArvore] = list(arquivos)

    def __iter__(self) -> Iterator[ArquivoArvore]:
        return iter(self.arquivos)

    def __len__(self) -> int:
        return len(self.arquivos)

    def __bool__(self) -> bool:
        return bool(self.arquivos)

    def com_extensao(self, *extensoes: str) -> list[ArquivoArvore]:
        ext = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensoes}
        return [a for a in self.arquivos if a.extensao in ext]

    def procurar(self, nome: str) -> Optional[ArquivoArvore]:
        """O arquivo com este nome (o mais raso, se houver varios)."""
        achados = [a for a in self.arquivos if a.nome.lower() == nome.lower()]
        return min(achados, key=lambda a: a.caminho.count("/")) if achados else None

    def pastas(self) -> list[str]:
        return sorted({a.pasta for a in self.arquivos})


@dataclass
class Unidade:
    """Uma parte do envio a ler: um arquivo, um grupo (ex. dados + calibracao)
    ou um trecho. `rotulo` aparece no progresso e nos erros; `dados` leva o que
    o reconhecer ja descobriu (ex. a calibracao lida), e precisa ser picklable
    se a leitura for em paralelo."""

    rotulo: str
    arquivos: list = field(default_factory=list)
    dados: dict = field(default_factory=dict)

    @property
    def arquivo(self) -> ArquivoArvore:
        return self.arquivos[0]


@dataclass
class PlanoImportacao:
    """Resultado do reconhecer. `ignorados`: lista de (arquivo ou caminho, motivo).
    `metadados`: o que o envio revela; "numero_serie" (texto ou lista) e
    conferido com o cadastro (aviso se for de outro equipamento)."""

    unidades: list[Unidade] = field(default_factory=list)
    ignorados: list = field(default_factory=list)
    metadados: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Recusa:
    """O envio nao tem a estrutura esperada. `motivo` e mostrado ao usuario."""

    motivo: str


@dataclass(frozen=True)
class Ingestao:
    """Como o plugin le um envio.

    tabela:     classe SQLAlchemy das leituras (com equipamento_id e envio_id);
    reconhecer: reconhecer(arvore, verificar=False) -> PlanoImportacao | Recusa
                (verificar=True: so diga se a arvore e deste sensor, sem ler conteudo pesado);
    ler:        ler(unidade) -> iteravel de dicts (colunas da tabela, sem ids);
                precisa ser uma funcao de modulo se leitura_paralela;
    chave:      colunas da chave natural (deduplicacao no envio e contra o banco);
    coluna_tempo: coluna com o horario da leitura (periodo do envio);
    coluna_corrompido: coluna booleana de leitura corrompida (guardada para diagnostico);
    coluna_numero_serie: coluna conferida com o numero de serie do cadastro;
    leitura_paralela: as unidades podem ser lidas em processos separados."""

    tabela: Any
    reconhecer: Callable[..., Union[PlanoImportacao, Recusa]]
    ler: Callable[[Unidade], Iterable[dict]]
    chave: tuple[str, ...] = ("equipamento_id", "tempo")
    coluna_tempo: str = "tempo"
    coluna_corrompido: Optional[str] = None
    coluna_numero_serie: Optional[str] = None
    leitura_paralela: bool = False
    tamanho_lote: int = 2000


# ============================================================================ exportacao

@dataclass
class ContextoExportacao:
    """O que exportar() recebe alem do periodo: o equipamento, a qualidade de
    cada leitura (qualidade(tempo) -> "" ou os codigos das regras, separados por
    ";") e a instituicao da instalacao (marca.toml; "" se nao configurada),
    para metadados como o atributo `institution` do NetCDF."""

    equipamento: Any
    qualidade: Callable[[Any], str] = field(default=lambda _tempo: "")
    instituicao: str = ""


@dataclass(frozen=True)
class Exportacao:
    """formatos: os FormatoExportacao oferecidos; exportar(sessao, equipamento_id,
    inicio, fim, formato, destino, contexto) -> ResultadoExportacao, lendo e
    escrevendo em blocos. As exportacoes levam a coluna de qualidade."""

    formatos: tuple
    exportar: Callable[..., ResultadoExportacao]


# ============================================================================ plugin

@dataclass(frozen=True)
class Plugin:
    """Um tipo de sensor completo. Obrigatorios: manifesto, modelos/migracoes e ingestao."""

    manifesto: Manifesto
    ingestao: Ingestao
    modelos: tuple = ()
    migracoes: Optional[Path] = None          # versoes Alembic (branch_labels=(codigo,))
    ficha: tuple = ()                          # Campo, ...
    versao_ficha: int = 1
    migrar_atributos: Optional[Callable[[dict, int], dict]] = None   # (atributos, versao_antiga) -> novos
    regras: tuple = ()                         # Regra, ...
    consultas: Optional[str] = None            # modulo importado sob demanda
    exportacao: Optional[Exportacao] = None
    interface: Optional[str] = None            # modulo com ABAS (PySide6), importado sob demanda
    rotas: Optional[Callable[[], Any]] = None  # () -> fastapi.APIRouter
    amostra: Optional[Path] = None             # dados reais minimos para o kit de conformidade

    @property
    def codigo(self) -> str:
        return self.manifesto.codigo

    @property
    def nome(self) -> str:
        return self.manifesto.nome

    @property
    def versao(self) -> str:
        return self.manifesto.versao

    def modulo_consultas(self):
        if not self.consultas:
            return None
        import importlib
        return importlib.import_module(self.consultas)

    def modulo_interface(self):
        if not self.interface:
            return None
        import importlib
        return importlib.import_module(self.interface)

    def formatos_exportacao(self) -> list[FormatoExportacao]:
        return list(self.exportacao.formatos) if self.exportacao else []

    def campo_ficha(self, chave: str) -> Optional[Campo]:
        return next((c for c in self.ficha if c.chave == chave), None)


# ============================================================================ acesso ao nucleo

def sessao_autorizada(usuario: Usuario, perfil: str):
    """Sessao (uma transacao) depois de conferir no banco o usuario e o perfil.
    Use nas consultas do plugin: `with sessao_autorizada(u, "leitura") as (sessao, atual):`."""
    from app import servico
    return servico.sessao_autorizada(usuario, perfil)


def obter_equipamento_orm(sessao, equipamento_id: int, tipo_sensor: Optional[str] = None):
    """Equipamento (ORM) da sessao; NaoEncontrado se nao existe; erro se for de outro tipo."""
    from app import servico
    return servico.obter_equipamento_orm(sessao, equipamento_id, tipo_sensor)


def usuario_da_api():
    """Dependencia FastAPI do usuario logado (para as rotas do plugin):
    `usuario=Depends(usuario_da_api())`."""
    from app.api.autenticacao import usuario_atual
    return usuario_atual
