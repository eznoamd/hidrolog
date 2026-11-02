"""Central de ajuda: um tópico por arquivo Markdown em `topicos/`, agrupados
por público. Os textos são do app (genéricos, sem nenhum sensor específico).

    for grupo, lista in agrupados("cadastro"): ...
    texto(TOPICO["importar"])            # Markdown
    buscar("senha", "leitura")           # tópicos com o termo, na ordem da lista

Link entre tópicos, dentro do Markdown: [Importar dados](ajuda:importar).
Para acrescentar um tópico: crie o .md em topicos/ e uma linha em TOPICOS.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from importlib import resources

ESQUEMA_LINK = "ajuda"

GRUPOS = (
    ("comecar", "Primeiros passos"),
    ("uso", "Usando o Hidrolog"),
    ("admin", "Administração"),
)

MASTER = frozenset({"master"})


@dataclass(frozen=True)
class Topico:
    chave: str                       # nome do arquivo (sem .md) e alvo dos links ajuda:<chave>
    titulo: str
    grupo: str
    perfis: frozenset[str] | None = None   # None: todos os perfis

    def visivel_para(self, perfil: str | None) -> bool:
        return self.perfis is None or perfil in self.perfis


TOPICOS: tuple[Topico, ...] = (
    Topico("boas-vindas", "O que é o Hidrolog", "comecar"),
    Topico("primeiros-passos", "Entrar e se localizar", "comecar"),
    Topico("perfis", "Perfis e permissões", "comecar"),
    Topico("inicio", "Início", "uso"),
    Topico("equipamentos", "Equipamentos", "uso"),
    Topico("importar", "Importar dados", "uso"),
    Topico("historico", "Histórico de envios", "uso"),
    Topico("exportar", "Exportar dados", "uso"),
    Topico("qualidade", "Qualidade dos dados", "uso"),
    Topico("conta", "Minha conta", "uso"),
    Topico("problemas", "Problemas comuns", "uso"),
    Topico("usuarios", "Usuários", "admin", MASTER),
    Topico("plugins", "Plugins de sensor", "admin", MASTER),
    Topico("instalacao", "Instalação, dados e cópias", "admin", MASTER),
    Topico("criar-plugin", "Criar um plugin", "admin", MASTER),
)
TOPICO = {t.chave: t for t in TOPICOS}


def topicos(perfil: str | None) -> list[Topico]:
    return [t for t in TOPICOS if t.visivel_para(perfil)]


def agrupados(perfil: str | None) -> list[tuple[str, list[Topico]]]:
    """[(título do grupo, tópicos)] com os grupos que têm algum tópico visível."""
    visiveis = topicos(perfil)
    saida = []
    for chave, titulo in GRUPOS:
        lista = [t for t in visiveis if t.grupo == chave]
        if lista:
            saida.append((titulo, lista))
    return saida


def texto(topico: Topico) -> str:
    return resources.files(__package__).joinpath("topicos", f"{topico.chave}.md").read_text(encoding="utf-8")


def _normalizar(s: str) -> str:
    """Minúsculas e sem acento, para a busca achar "cópia" com "copia"."""
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def buscar(termo: str, perfil: str | None) -> list[Topico]:
    """Tópicos visíveis que têm todas as palavras do termo (no título ou no texto)."""
    palavras = _normalizar(termo).split()
    if not palavras:
        return topicos(perfil)
    achados = []
    for t in topicos(perfil):
        conteudo = _normalizar(t.titulo + "\n" + texto(t))
        if all(p in conteudo for p in palavras):
            achados.append(t)
    return achados
