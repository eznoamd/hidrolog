"""
Componentes PySide6 reutilizáveis do app de sensores (independentes de sensor).

    from design.componentes import JanelaPrincipal, CartaoMetrica, TabelaFiltravel, Coluna, ...
"""

from . import formatos
from .abas import Abas
from .abertura import TelaAbertura
from .arquivos import AreaSoltarArquivo, DialogoArquivoOuPasta
from .base import Botao, Cartao, Divisoria, Pagina, rotulo
from .carregando import Carregando, IndicadorCarregamento, SobreposicaoCarregamento
from .dialogos import DialogoConfirmacao, DialogoSenha, FaixaAviso
from .figura import FiguraIncorporada
from .formulario import FormularioFicha
from .importacao import PainelImportacao, ResumoImportacao
from .login import TelaLogin
from .logo import LogoInstituicao, LogoMarca, caminho_logo
from .mapa import MapaSeletor
from .metrica import CartaoMetrica
from .periodo import SeletorEquipamentoPeriodo, SeletorPeriodo
from .selo import Selo, selo_perfil
from .usuario import Avatar, MenuUsuario, PainelUsuario, iniciais
from .shell import JanelaPrincipal, PaginaNaoImplementada
from .tabela import Coluna, TabelaFiltravel
from .vazio import EstadoVazio

__all__ = [
    "Abas", "AreaSoltarArquivo", "Avatar", "MenuUsuario", "PainelUsuario", "iniciais", "DialogoArquivoOuPasta", "Botao", "Carregando", "Cartao", "CartaoMetrica", "Coluna",
    "DialogoConfirmacao", "DialogoSenha", "Divisoria", "EstadoVazio", "FaixaAviso", "FiguraIncorporada", "FormularioFicha", "IndicadorCarregamento",
    "JanelaPrincipal", "LogoInstituicao", "LogoMarca", "MapaSeletor", "Pagina", "PaginaNaoImplementada", "PainelImportacao",
    "ResumoImportacao", "Selo", "SeletorEquipamentoPeriodo", "SeletorPeriodo", "SobreposicaoCarregamento", "TabelaFiltravel", "TelaAbertura", "TelaLogin", "caminho_logo", "formatos",
    "rotulo", "selo_perfil",
]
