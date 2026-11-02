"""Plugin de teste "pluviometro com datalogger": um CSV com milhares de linhas
(data_hora;pulsos). reconhecer: o .csv com a coluna "pulsos" e a unidade
(recusa sem ela); ler: uma leitura por linha, em fluxo (arquivo maior que o
limite de leitura inteira passa, porque nao e carregado na memoria)."""

from datetime import datetime
from pathlib import Path

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from hidrolog_nucleo.plugin import Base, Ingestao, Manifesto, PlanoImportacao, Plugin, Recusa, Unidade


class PluvioLeitura(Base):
    __tablename__ = "teste_pluvio_leitura"
    __table_args__ = (UniqueConstraint("equipamento_id", "tempo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamento.id"))
    envio_id: Mapped[int] = mapped_column(ForeignKey("envio.id"))
    tempo: Mapped[datetime] = mapped_column(DateTime)
    pulsos: Mapped[int] = mapped_column(Integer)


def reconhecer(arvore, verificar=False):
    csvs = arvore.com_extensao(".csv")
    if not csvs:
        return Recusa("nenhum .csv do datalogger encontrado")
    unidades = []
    for a in csvs:
        if "pulsos" not in a.primeira_linha().lower():
            return Recusa(f"{a.nome}: falta a coluna 'pulsos'")
        unidades.append(Unidade(a.nome, arquivos=[a]))
    outros = [a for a in arvore if a not in csvs]
    return PlanoImportacao(unidades, ignorados=[(a, "nao e .csv") for a in outros])


def ler(unidade):
    for linha in unidade.arquivo.linhas_csv():
        yield {"tempo": datetime.strptime(linha["data_hora"], "%Y-%m-%d %H:%M:%S"),
               "pulsos": int(linha["pulsos"])}


PLUGIN = Plugin(
    manifesto=Manifesto(codigo="testepluvio", nome="Pluviômetro de teste (CSV longo)", versao="0.1.0",
                        contrato="1.x", modulo="tests.plugins_teste.csvlongo"),
    modelos=(PluvioLeitura,),
    migracoes=Path(__file__).parent / "migracoes",
    ingestao=Ingestao(tabela=PluvioLeitura, reconhecer=reconhecer, ler=ler, tamanho_lote=500),
)
