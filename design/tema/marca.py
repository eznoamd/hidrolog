"""
Identidade do aplicativo num ponto só.

O repositório é genérico: sem configuração, o app se chama "Hidrolog", não
tem laboratório nem instituição, e o lugar das logos mostra o texto "LOGO".
Cada instalação põe a sua identidade numa **pasta de marca**, fora do código:

    <pasta de marca>/
    ├── marca.toml          nomes, siglas, cores, posição inicial do mapa
    ├── logo.svg|png        logo do laboratório
    ├── logo-escura.svg|png versão para o tema escuro (opcional; ver gerar_logo_escura.py)
    ├── instituicao.svg|png logo da instituição (opcional)
    └── icone.svg|png       ícone da janela (opcional)

    # marca.toml (todas as chaves são opcionais)
    nome_app = "Hidrolog"
    descricao = "Cadastro e consulta dos dados dos sensores ambientais do laboratório."

    [laboratorio]
    sigla = "LAB"
    nome = "Laboratório de …"

    [instituicao]
    sigla = "UNIV"
    nome = "Universidade …"

    [mapa]
    posicao_inicial = [-15.7939, -47.8828]     # latitude, longitude

    [cores]                                     # cor de ação; confira o AA com tema/contraste.py
    primaria_claro = "#1D6A92"
    primaria_escuro = "#6DB6DB"

O app carrega a pasta ao abrir (carregar_marca_da_instalacao); componentes,
login, título da janela e catálogo leem só daqui:

    m = marca_atual()
    m.nome_app            # "Hidrolog"
    m.titulo_janela       # "Hidrolog — LAB" (ou só "Hidrolog" sem laboratório)
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass, replace
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:          # Python 3.10
    import tomli as tomllib

from . import tokens

ARQUIVO_MARCA = "marca.toml"
# sem posição configurada, o mapa abre no centro do Brasil (Brasília)
POSICAO_PADRAO_MAPA = (-15.7939, -47.8828)


@dataclass(frozen=True)
class Marca:
    nome_app: str = "Hidrolog"                        # marca tipográfica do app (sem logo própria)
    descricao: str = "Cadastro e consulta dos dados dos sensores ambientais do laboratório."
    laboratorio: str | None = None                    # sigla (assinatura; acima do nome do app)
    laboratorio_completo: str | None = None
    instituicao: str | None = None                    # nome por extenso (rodapé do login)
    instituicao_sigla: str | None = None
    # arquivos (None = reserva: o texto "LOGO" no lugar da imagem)
    logo: Path | None = None
    logo_instituicao: Path | None = None
    icone_app: Path | None = None
    # versão para o tema escuro (letreiro claro). Sem ela, a logo normal vai
    # sobre uma placa clara no tema escuro.
    logo_escura: Path | None = None
    logo_precisa_placa_no_escuro: bool = True      # só vale quando não há logo_escura
    # (latitude, longitude) onde o mapa de escolha de posição começa
    posicao_padrao_mapa: tuple[float, float] = POSICAO_PADRAO_MAPA
    # cores da marca por modo (chaves de tokens.CHAVES_MARCA); None = padrão dos tokens
    cores: dict[str, dict[str, str]] | None = None

    @property
    def cor_primaria(self) -> dict[str, str]:
        """{"claro": hex, "escuro": hex} da cor primária efetiva."""
        return {m: tokens.cores(m)["primaria"] for m in tokens.MODOS}

    @property
    def titulo_janela(self) -> str:
        """Título da janela: "Hidrolog — LAB", ou só "Hidrolog" sem laboratório."""
        return f"{self.nome_app} \u2014 {self.laboratorio}" if self.laboratorio else self.nome_app

    @property
    def assinatura(self) -> str:
        """Texto curto de rodapé, ex.: "LAB · UNIV" ("" sem laboratório nem instituição)."""
        return " · ".join(x for x in (self.laboratorio, self.instituicao_sigla) if x)

    @classmethod
    def da_pasta(cls, pasta: str | Path) -> "Marca":
        """Marca de uma pasta de marca (marca.toml + imagens). Pasta inexistente
        ou vazia = a marca genérica. Chaves desconhecidas são ignoradas."""
        pasta = Path(pasta)
        if not pasta.is_dir():
            return cls()

        def arquivo(*nomes: str) -> Path | None:
            for nome in nomes:
                if (pasta / nome).is_file():
                    return pasta / nome
            return None

        dados: dict = {}
        if (pasta / ARQUIVO_MARCA).is_file():
            dados = tomllib.loads((pasta / ARQUIVO_MARCA).read_text(encoding="utf-8-sig"))  # aceita BOM
        lab, inst = dados.get("laboratorio", {}), dados.get("instituicao", {})
        mapa, cores = dados.get("mapa", {}), dados.get("cores", {})

        def texto(secao: dict, chave: str) -> str | None:
            """Campo de texto; vazio (ex.: deixado em branco no instalador) conta como ausente."""
            valor = str(secao.get(chave) or "").strip()
            return valor or None

        campos: dict = dict(
            laboratorio=texto(lab, "sigla"), laboratorio_completo=texto(lab, "nome"),
            instituicao=texto(inst, "nome"), instituicao_sigla=texto(inst, "sigla"),
            logo=arquivo(lab.get("logo", ""), "logo.svg", "logo.png"),
            logo_escura=arquivo(lab.get("logo_escura", ""), "logo-escura.svg", "logo-escura.png"),
            logo_instituicao=arquivo(inst.get("logo", ""), "instituicao.svg", "instituicao.png"),
            icone_app=arquivo("icone.svg", "icone.png"),
        )
        for chave in ("nome_app", "descricao"):
            if dados.get(chave):
                campos[chave] = dados[chave]
        if len(mapa.get("posicao_inicial", ())) == 2:
            campos["posicao_padrao_mapa"] = tuple(float(v) for v in mapa["posicao_inicial"])
        if cores.get("primaria_claro") and cores.get("primaria_escuro"):
            campos["cores"] = {"claro": derivar_cores_marca(cores["primaria_claro"], "claro"),
                               "escuro": derivar_cores_marca(cores["primaria_escuro"], "escuro")}
        return cls(**campos)


_marca = Marca()


def marca_atual() -> Marca:
    return _marca


def definir_marca(marca: Marca | None = None, **campos) -> Marca:
    """Define a marca do app. Aceita uma Marca ou só os campos a mudar:
    definir_marca(nome_app="Outro nome"). Chame antes de aplicar_tema()."""
    global _marca
    _marca = marca or replace(_marca, **campos)
    tokens.definir_cores_marca(_marca.cores)
    return _marca


def carregar_marca_da_instalacao(pasta: str | Path) -> Marca:
    """Lê a pasta de marca da instalação e a torna a marca do app (genérica se
    a pasta não existir). Chame antes de aplicar_tema()."""
    return definir_marca(Marca.da_pasta(pasta))


def derivar_cores_marca(primaria: str, modo: str = "claro") -> dict[str, str]:
    """Deriva hover, pressionada, suave, texto, foco e seleção de UMA cor.
    Para o tema claro, passe um tom escuro o bastante para texto branco (≥ 4,5:1);
    para o escuro, um tom claro. Confira com tema/contraste.py."""
    def hls(h):
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return colorsys.rgb_to_hls(r, g, b)

    def hexa(hh, ll, ss):
        r, g, b = colorsys.hls_to_rgb(hh, max(0, min(1, ll)), max(0, min(1, ss)))
        return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))

    h, l, s = hls(primaria)
    if modo == "claro":
        return {"primaria": primaria.upper(), "primaria_hover": hexa(h, l - 0.06, s),
                "primaria_pressionada": hexa(h, l - 0.12, s), "primaria_suave": hexa(h, 0.93, s * 0.55),
                "primaria_texto": hexa(h, l - 0.04, s), "foco": primaria.upper(), "selecao": hexa(h, 0.88, s * 0.5)}
    return {"primaria": primaria.upper(), "primaria_hover": hexa(h, l + 0.07, s),
            "primaria_pressionada": hexa(h, l + 0.13, s), "primaria_suave": hexa(h, 0.17, s * 0.4),
            "primaria_texto": hexa(h, l + 0.05, s), "foco": hexa(h, l + 0.05, s), "selecao": hexa(h, 0.21, s * 0.4)}
