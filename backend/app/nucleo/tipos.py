"""O que a camada de servico devolve: dataclasses simples e imutaveis, sem
ligacao com a sessao do banco (podem ir para a interface ou virar JSON)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Optional

PERFIS = ("leitura", "cadastro", "master")   # cada um inclui os anteriores


@dataclass(frozen=True)
class Usuario:
    id: int
    login: str
    nome: str
    perfil: str           # "master", "cadastro" ou "leitura"
    ativo: bool
    criado_em: datetime

    def pode(self, perfil: str) -> bool:
        """True se o perfil deste usuario inclui `perfil` (master > cadastro > leitura)."""
        return PERFIS.index(self.perfil) >= PERFIS.index(perfil)


@dataclass(frozen=True)
class TipoSensor:
    codigo: str
    nome: str


@dataclass(frozen=True)
class Equipamento:
    id: int
    tipo_sensor: str
    nome: str
    numero_serie: Optional[str]
    local: Optional[str]
    observacoes: Optional[str]
    ativo: bool
    criado_em: datetime
    latitude: Optional[float] = None          # graus decimais (WGS84)
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None
    instalado_em: Optional[date] = None
    atributos: dict = field(default_factory=dict, hash=False, compare=True)   # ficha do plugin
    versao_ficha: Optional[int] = None


@dataclass(frozen=True)
class ResumoEnvio:
    id: int
    equipamento_id: int
    equipamento: str
    tipo_sensor: str
    usuario: str                 # login de quem enviou
    recebido_em: datetime
    canal: str                   # "local" ou "upload"
    tipo: str                    # "zip", "rar", "pasta", "arquivos" ou "misto"
    origem: str
    arquivos_recebidos: int
    ignorados: int
    leituras: int
    validas: int
    corrompidas: int
    novas: int
    duplicadas: int
    inicio: Optional[datetime]   # periodo coberto pelo envio
    fim: Optional[datetime]
    duracao_s: float
    avisos: list[str] = field(default_factory=list)
    arquivos_ignorados: list[str] = field(default_factory=list)  # ate 50, so no retorno da importacao
    ocorrencias: int = 0          # ocorrencias de qualidade criadas pela importacao (so no retorno dela)

    def como_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResumoImportacao:
    """Contagens de uma importacao (app.nucleo.ingestao); o nucleo grava no envio."""
    leituras: int = 0
    validas: int = 0
    corrompidas: int = 0
    novas: int = 0
    duplicadas: int = 0
    ignorados: int = 0               # arquivos com nome do sensor que o plugin descartou
    inicio: Optional[datetime] = None
    fim: Optional[datetime] = None
    avisos: list[str] = field(default_factory=list)
    arquivos_ignorados: list[str] = field(default_factory=list)
    metadados: dict = field(default_factory=dict)   # o que o reconhecer do plugin revelou


@dataclass(frozen=True)
class ResumoLeituras:
    """Leituras de um equipamento num periodo (generico, pela tabela do plugin)."""
    equipamento_id: int
    leituras: int
    validas: int
    corrompidas: int
    inicio: Optional[datetime]
    fim: Optional[datetime]


@dataclass(frozen=True)
class FormatoExportacao:
    codigo: str          # ex. "csv", "netcdf"
    nome: str            # ex. "CSV (uma linha por leitura)"
    extensao: str        # ex. ".csv", ".nc"
    tipo_mime: str = "application/octet-stream"


@dataclass
class ResultadoExportacao:
    """O que o plugin devolve de exportar(); o nucleo completa o resumo."""
    leituras: int = 0
    inicio: Optional[datetime] = None
    fim: Optional[datetime] = None


@dataclass(frozen=True)
class ResumoExportacao:
    caminho: str                 # arquivo gerado
    formato: str
    equipamento_id: int
    leituras: int
    inicio: Optional[datetime]   # periodo efetivamente exportado (primeira e ultima leitura)
    fim: Optional[datetime]
    tamanho_bytes: int


@dataclass(frozen=True)
class InfoPlugin:
    """Um plugin na tela Plugins. estado: ativo, desativado, incompativel,
    com falha, conflito ou instalado (ainda nao carregado: reinicie)."""
    codigo: str
    nome: str
    versao: str
    contrato: str
    origem: str                  # interno, pasta, zip, github ou registro
    estado: str
    motivo: str = ""
    url: str = ""
    tag: str = ""
    sha256: str = ""
    caminho: str = ""
    instalado_em: Optional[datetime] = None
    instalado_por: str = ""
    versoes: list = field(default_factory=list)     # versoes guardadas na pasta de plugins
    pendente: str = ""                              # o que muda ao reiniciar o app


@dataclass(frozen=True)
class RegistroAuditoria:
    id: int
    quando: datetime
    login: str
    acao: str
    codigo: Optional[str]
    versao: Optional[str]
    origem: Optional[str]
    resultado: str
    detalhes: Optional[str]


@dataclass(frozen=True)
class InfoRegra:
    """Uma regra de qualidade do plugin, com os parametros valendo para o equipamento."""
    codigo: str
    descricao: str
    nivel: str                    # leitura, envio ou equipamento
    severidade: str               # aviso, suspeita ou alerta
    parametros: dict              # efetivos (padrao + ajustes do equipamento)
    padrao: dict
    ativa: bool
    declarativa: bool
    ajuda_parametros: dict = field(default_factory=dict)
    alterada_por: str = ""
    alterada_em: Optional[datetime] = None


@dataclass(frozen=True)
class InfoOcorrencia:
    id: int
    equipamento_id: int
    equipamento: str
    envio_id: Optional[int]
    tempo: Optional[datetime]
    codigo_regra: str
    nivel: str
    severidade: str
    mensagem: str
    criada_em: datetime
    resolvida_em: Optional[datetime]
    resolvida_por: str            # login; "" = aberta, ou resolvida sozinha (a condicao deixou de valer)


@dataclass(frozen=True)
class ResumoQualidade:
    """Ocorrencias abertas de um equipamento, por severidade."""
    equipamento_id: int
    alertas: int = 0
    suspeitas: int = 0
    avisos: int = 0

    @property
    def total(self) -> int:
        return self.alertas + self.suspeitas + self.avisos
