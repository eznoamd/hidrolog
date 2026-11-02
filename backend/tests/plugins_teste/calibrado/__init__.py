"""Plugin de teste "sensor com calibracao": arquivos .bin (registros de 10
bytes: segundos desde 1970 em int64 LE + valor bruto int16 LE) e um
calibracao.json ({"fator": f, "deslocamento": d}) que vale para todos.
reconhecer: le a calibracao (recusa se faltar) e a poe nos metadados e em
cada unidade; ler: cada .bin -> leituras ja calibradas (valor = bruto * f + d).
As unidades podem ser lidas em paralelo (a calibracao vai junto, em dados)."""

import json
import struct
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from hidrolog_nucleo.plugin import Base, Ingestao, Manifesto, PlanoImportacao, Plugin, Recusa, Unidade

REGISTRO = struct.Struct("<qh")


class CalibradoLeitura(Base):
    __tablename__ = "teste_calibrado_leitura"
    __table_args__ = (UniqueConstraint("equipamento_id", "tempo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipamento_id: Mapped[int] = mapped_column(ForeignKey("equipamento.id"))
    envio_id: Mapped[int] = mapped_column(ForeignKey("envio.id"))
    tempo: Mapped[datetime] = mapped_column(DateTime)
    bruto: Mapped[int] = mapped_column(Integer)
    valor: Mapped[float] = mapped_column(Float)


def reconhecer(arvore, verificar=False):
    calibracao = arvore.procurar("calibracao.json")
    if calibracao is None:
        return Recusa("falta calibracao.json na raiz do envio")
    bins = arvore.com_extensao(".bin")
    if not bins:
        return Recusa("nenhum arquivo .bin de dados")
    if verificar:
        return PlanoImportacao([Unidade(a.caminho, [a]) for a in bins])
    try:
        cal = json.loads(calibracao.texto())
        cal = {"fator": float(cal["fator"]), "deslocamento": float(cal.get("deslocamento", 0.0))}
    except (ValueError, KeyError, TypeError) as erro:
        return Recusa(f"calibracao.json invalido ({erro})")
    usados = set(bins) | {calibracao}
    return PlanoImportacao(
        unidades=[Unidade(a.caminho, [a], dados={"calibracao": cal}) for a in bins],
        ignorados=[(a, "nao e dado nem calibracao") for a in arvore if a not in usados],
        metadados={"calibracao": cal})


def ler(unidade):
    cal = unidade.dados["calibracao"]
    conteudo = unidade.arquivo.ler()
    for (segundos, bruto) in REGISTRO.iter_unpack(conteudo):
        tempo = datetime.fromtimestamp(segundos, timezone.utc).replace(tzinfo=None)
        yield {"tempo": tempo, "bruto": bruto, "valor": bruto * cal["fator"] + cal["deslocamento"]}


PLUGIN = Plugin(
    manifesto=Manifesto(codigo="testecalibrado", nome="Sensor de teste com calibração", versao="0.1.0",
                        contrato="1.x", modulo="tests.plugins_teste.calibrado"),
    modelos=(CalibradoLeitura,),
    migracoes=Path(__file__).parent / "migracoes",
    ingestao=Ingestao(tabela=CalibradoLeitura, reconhecer=reconhecer, ler=ler, leitura_paralela=True),
)
