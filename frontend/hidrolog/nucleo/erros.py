"""Erros do backend -> mensagens em português para a tela.

A tela nunca mostra traceback: o detalhe vai para o log em arquivo
(configuracao.caminho_log()) e o usuário vê o que aconteceu e o que fazer.
"""

from __future__ import annotations

import logging
import re

from app.nucleo.erros import (
    Conflito,
    EnvioRecusado,
    ErroAutenticacao,
    ErroEnvio,
    ErroPermissao,
    ErroRarSemFerramenta,
    ErroServico,
    ErroValidacao,
    LimiteExcedido,
    NaoEncontrado,
)
from app.nucleo.gerenciador import OperacaoCancelada, SenhaIncorreta

log = logging.getLogger("hidrolog.erros")

NOMES_PERFIL = {"master": "Master", "cadastro": "Cadastro", "leitura": "Leitura"}

INSTRUCAO_RAR = (
    "Este .rar está comprimido e o computador não tem um programa para abri-lo. "
    "Instale um no terminal com  sudo apt install unar  (ou unrar) e tente de novo. "
    "Outra saída: envie a pasta do cartão ou um .zip."
)


class TarefaCancelada(Exception):
    """Levantada pelo próprio front para interromper uma tarefa (ex.: importação)."""


# trechos conhecidos das mensagens do backend (sem acento) -> português da interface
_TRADUCOES = [
    (r"nao", "não"), (r"usuario", "usuário"), (r"invalido", "inválido"), (r"permitido", "permitido"),
    (r"numero de serie", "número de série"), (r"esta desativado", "está desativado"),
    (r"ja existe", "já existe"), (r"caminho nao encontrado", "caminho não encontrado"),
    (r"arquivo de dados maior que", "arquivo de dados maior que"), (r"descompactar", "descompactar"),
    (r"importacao", "importação"), (r"simultanea", "simultânea"), (r"diferente do cadastrado", "diferente do cadastrado"),
    (r"versao", "versão"), (r"migracoes", "migrações"), (r"dependencias", "dependências"), (r"incompativel", "incompatível"),
    (r"repositorio", "repositório"), (r"repositorios", "repositórios"), (r"confiaveis", "confiáveis"),
    (r"codigo", "código"), (r"modulo", "módulo"), (r"ja esta", "já está"), (r"leitura", "leitura"),
    (r"invalida", "inválida"), (r"maximo", "máximo"), (r"minimo", "mínimo"), (r"numero", "número"),
    (r"obrigatorio", "obrigatório"), (r"e igual a atual", "é igual à atual"), (r"opcoes", "opções"), (r"ficha do equipamento", "ficha do equipamento"),
]


def acentuar(texto: str) -> str:
    """Põe acento nas palavras mais comuns das mensagens do backend e a
    primeira letra em maiúscula (o backend escreve sem acento)."""
    for padrao, troca in _TRADUCOES:
        texto = re.sub(rf"\b{padrao}\b", troca, texto)
    texto = texto.strip()
    if texto and not texto.endswith((".", "!", "?")):
        texto += "."
    return texto[:1].upper() + texto[1:]


def mensagem(erro: BaseException, perfil: str | None = None) -> str:
    """Texto para o usuário. `perfil` deixa a mensagem de permissão mais clara."""
    if isinstance(erro, TarefaCancelada):
        return "Operação cancelada. Nada foi gravado."
    if isinstance(erro, ErroRarSemFerramenta):
        return INSTRUCAO_RAR
    if isinstance(erro, SenhaIncorreta):
        return f"Senha incorreta. Restam {erro.restantes} tentativa(s)."
    if isinstance(erro, OperacaoCancelada):
        return "Três senhas erradas: a operação foi cancelada e registrada na auditoria."
    if isinstance(erro, EnvioRecusado):
        return f"Estes arquivos não têm a estrutura que este tipo de sensor espera: {acentuar(str(erro))}"
    if isinstance(erro, ErroValidacao):
        return "Revise os campos destacados. " + acentuar(str(erro))
    if isinstance(erro, ErroAutenticacao):
        return "Sua sessão não é mais válida (o usuário pode ter sido desativado). Entre de novo."
    if isinstance(erro, ErroPermissao):
        detalhe = str(erro)
        if "master" in detalhe and "comando de linha" in detalhe:
            return "O perfil master só é criado pelo comando de linha do backend."
        if "master" in detalhe and "desativado" in detalhe:
            return "Um usuário master não pode ser desativado pelo app."
        if "master" in detalhe:
            return "O perfil master não é dado nem retirado pelo app."
        nome = NOMES_PERFIL.get(perfil or "", "")
        return (f"Seu perfil ({nome}) não permite esta ação. " if nome else "Seu perfil não permite esta ação. ") + \
            "Peça a um usuário master se precisar dela."
    if isinstance(erro, LimiteExcedido):
        return f"O envio passa de um limite de segurança: {acentuar(str(erro))}"
    if isinstance(erro, ErroEnvio):
        return f"Não foi possível ler os arquivos enviados. {acentuar(str(erro))}"
    if isinstance(erro, NaoEncontrado):
        return "O registro pedido não foi encontrado. Ele pode ter sido alterado; atualize a página."
    if isinstance(erro, Conflito):
        return acentuar(str(erro))
    if isinstance(erro, ErroServico):
        return acentuar(str(erro))
    if isinstance(erro, PermissionError):
        return "Sem permissão para gravar ou ler neste local. Escolha outra pasta."
    if isinstance(erro, FileNotFoundError):
        return "O arquivo ou a pasta não foi encontrado."
    if isinstance(erro, OSError):
        return f"Erro de leitura ou gravação no disco ({erro.strerror or 'erro de E/S'})."
    return "Ocorreu um erro inesperado. Os detalhes foram gravados no log do Hidrolog."


def registrar(erro: BaseException, contexto: str = "") -> None:
    """Grava o erro no log: erros esperados do serviço sem traceback, o resto com."""
    if isinstance(erro, (ErroServico, TarefaCancelada)):
        log.info("%s%s: %s", f"{contexto}: " if contexto else "", type(erro).__name__, erro)
    else:
        log.error("%s%s", f"{contexto}: " if contexto else "", type(erro).__name__,
                  exc_info=(type(erro), erro, erro.__traceback__))


def traduzir_aviso(aviso: str) -> str:
    """Aviso de um envio (texto do backend) em português da interface."""
    m = re.match(r"numero de serie nos arquivos \((.*)\) diferente do cadastrado no equipamento \((.*)\)", aviso)
    if m:
        return (f"O número de série nos arquivos ({m.group(1)}) é diferente do cadastrado no equipamento "
                f"({m.group(2)}). Os dados entraram mesmo assim; confira se escolheu o equipamento certo.")
    return acentuar(aviso)
