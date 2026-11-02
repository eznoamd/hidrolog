"""Plugin falso minimo: prova que um segundo tipo de sensor entra sem
mexer no nucleo. Arquivos "falso_AAAAMMDDHHMMSS.csv" com "valor;N"; um valor
ilegivel vira leitura corrompida (guardada para diagnostico)."""

from datetime import datetime
from pathlib import Path

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from hidrolog_nucleo.plugin import Base, Ingestao, Manifesto, PlanoImportacao, Plugin, Recusa, Unidade


class FalsoLeitura(Base):
    __tablename__ = "falso_leitura"
    __table_args__ = (UniqueConstraint("equipamento_id", "tempo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamento.id"))
    envio_id: Mapped[int] = mapped_column(ForeignKey("envio.id"))
    tempo: Mapped[datetime] = mapped_column(DateTime)
    valor: Mapped[float | None] = mapped_column(Float)
    corrompido: Mapped[bool] = mapped_column(Boolean, default=False)


def _eh_dado(nome: str) -> bool:
    return nome.startswith("falso_") and nome.endswith(".csv")


def reconhecer(arvore, verificar=False):
    dados = [a for a in arvore if _eh_dado(a.nome)]
    if not dados:
        return Recusa("nenhum arquivo falso_*.csv")
    return PlanoImportacao([Unidade(a.caminho, [a]) for a in dados],
                           ignorados=[(a, "nao e do sensor falso") for a in arvore if not _eh_dado(a.nome)])


def ler(unidade):
    arquivo = unidade.arquivo
    tempo = datetime.strptime(Path(arquivo.nome).stem[6:], "%Y%m%d%H%M%S")
    try:
        valor = float(arquivo.texto().split(";")[1])
    except (IndexError, ValueError):
        yield {"tempo": tempo, "valor": None, "corrompido": True}
        return
    yield {"tempo": tempo, "valor": valor, "corrompido": False}


PLUGIN = Plugin(
    manifesto=Manifesto(codigo="falso", nome="Sensor falso (testes)", versao="0.1.0", contrato="1.x",
                        modulo="tests.plugin_falso"),
    modelos=(FalsoLeitura,),
    migracoes=Path(__file__).parent / "migracoes",
    ingestao=Ingestao(tabela=FalsoLeitura, reconhecer=reconhecer, ler=ler, coluna_corrompido="corrompido"),
)
