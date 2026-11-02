"""
Gerador do QSS dos dois temas a partir dos tokens.

    gerar_qss("claro", imagens)  -> str

Convenções de seletor usadas pelos componentes (propriedades dinâmicas):

    QPushButton[variante="primaria" | "secundaria" | "perigo" | "fantasma"]
    QPushButton#ItemNav                      item da barra lateral (checkable)
    QFrame[papel="cartao"]                   cartão com borda
    QLabel[papel="titulo_pagina" | "titulo" | "subtitulo" | "secundario"
           | "legenda" | "rotulo_campo" | "titulo_secao" | "erro"]
    QLabel[mono="true"]                      números (JetBrains Mono)
    QLineEdit[invalido="true"]               campo com erro

Para gravar os arquivos .qss estáticos (úteis no Qt Designer):
    python tema/qss.py   (a partir de design/)
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import tokens  # type: ignore
else:
    from . import tokens


def gerar_qss(modo: str, imagens: dict[str, str] | None = None) -> str:
    c = tokens.cores(modo)
    f = tokens.FONTE
    e = tokens.ESPACO
    r = tokens.RAIO
    d = tokens.DIMENSAO
    img = imagens or {}
    h = d["altura_controle"]
    fam = f'"{f["familia"]}"'
    mono = f'"{f["familia_mono"]}"'
    seta = f'image: url("{img["seta_baixo"]}");' if "seta_baixo" in img else ""
    seta_d = f'image: url("{img["seta_baixo_desab"]}");' if "seta_baixo_desab" in img else ""
    marca = f'image: url("{img["marca"]}");' if "marca" in img else ""

    return f"""
/* ===== tema {modo} (gerado de tokens.py; não editar à mão) ===== */

* {{
    font-family: {fam};
    font-size: {f["corpo"]}px;
    outline: 0;
}}
QWidget {{
    color: {c["texto"]};
    background: transparent;
    selection-background-color: {c["selecao"]};
    selection-color: {c["texto"]};
}}
QMainWindow, QDialog, QStackedWidget#AreaPaginas, QWidget#Fundo {{
    background: {c["fundo"]};
}}
QDialog {{ background: {c["superficie"]}; }}
QScrollArea, QScrollArea > QWidget > QWidget#ConteudoRolagem {{
    background: transparent;
    border: none;
}}

/* ---------- textos ---------- */
QLabel[papel="titulo_pagina"] {{ font-size: {f["titulo_pagina"]}px; font-weight: {f["peso_semi"]}; }}
QLabel[papel="titulo"] {{ font-size: {f["titulo"]}px; font-weight: {f["peso_semi"]}; }}
QLabel[papel="subtitulo"] {{ font-size: {f["subtitulo"]}px; font-weight: {f["peso_semi"]}; }}
QLabel[papel="titulo_cartao"] {{ font-size: {f["corpo"]}px; font-weight: {f["peso_semi"]}; }}
QLabel[papel="marca_app"] {{
    font-size: {f["marca_lateral"]}px; font-weight: {f["peso_negrito"]}; letter-spacing: -0.2px;
}}
QLabel[papel="marca_app_login"] {{
    font-size: {f["marca_login"]}px; font-weight: {f["peso_negrito"]}; letter-spacing: -0.4px;
}}
QLabel[papel="marca_lab"] {{
    color: {c["texto_terciario"]}; font-size: {f["legenda"]}px; font-weight: {f["peso_semi"]}; letter-spacing: 0.8px;
}}
/* vale também dentro de cartões (a regra "cartao QLabel" tira as bordas) */
QLabel[papel="logo_reserva"], QFrame[papel="cartao"] QLabel[papel="logo_reserva"] {{
    color: {c["texto_terciario"]}; border: 1px dashed {c["borda_forte"]}; border-radius: {r["sm"]}px;
    padding: 0px {e["sm"]}px;
}}
QLabel[papel="secundario"] {{ color: {c["texto_secundario"]}; }}
QLabel[papel="legenda"] {{ color: {c["texto_terciario"]}; font-size: {f["pequeno"]}px; }}
QLabel[papel="rotulo_campo"] {{ color: {c["texto_secundario"]}; font-size: {f["pequeno"]}px; font-weight: {f["peso_medio"]}; }}
QLabel[papel="titulo_secao"] {{
    color: {c["texto_terciario"]}; font-size: {f["legenda"]}px; font-weight: {f["peso_semi"]};
    letter-spacing: 0.6px;
}}
QLabel[papel="erro"] {{ color: {c["erro"]}; font-size: {f["pequeno"]}px; }}
QLabel[papel="link"] {{ color: {c["primaria_texto"]}; }}
QLabel[mono="true"] {{ font-family: {mono}; }}
QLabel[papel="metrica_valor"] {{
    font-family: {mono}; font-size: {f["metrica"]}px; font-weight: {f["peso_medio"]};
}}
QLabel[papel="metrica_unidade"] {{ color: {c["texto_terciario"]}; font-size: {f["corpo"]}px; }}


/* ---------- selos ---------- */
QLabel[papel="selo"] {{
    border-radius: {r["pilula"]}px; padding: 0 {e["sm"]}px;
    min-height: {d["altura_selo"]}px; max-height: {d["altura_selo"]}px;
    font-size: {f["pequeno"]}px; font-weight: {f["peso_semi"]};
}}
QLabel[papel="selo"][tom="neutro"] {{ background: {c["neutro_suave"]}; color: {c["neutro"]}; }}
QLabel[papel="selo"][tom="neutro"][solido="true"] {{ background: {c["neutro"]}; color: {c["superficie"]}; }}
QLabel[papel="selo"][tom="info"] {{ background: {c["info_suave"]}; color: {c["info"]}; }}
QLabel[papel="selo"][tom="info"][solido="true"] {{ background: {c["info"]}; color: {c["superficie"]}; }}
QLabel[papel="selo"][tom="sucesso"] {{ background: {c["sucesso_suave"]}; color: {c["sucesso"]}; }}
QLabel[papel="selo"][tom="sucesso"][solido="true"] {{ background: {c["sucesso"]}; color: {c["superficie"]}; }}
QLabel[papel="selo"][tom="alerta"] {{ background: {c["alerta_suave"]}; color: {c["alerta"]}; }}
QLabel[papel="selo"][tom="alerta"][solido="true"] {{ background: {c["alerta"]}; color: {c["superficie"]}; }}
QLabel[papel="selo"][tom="erro"] {{ background: {c["erro_suave"]}; color: {c["erro"]}; }}
QLabel[papel="selo"][tom="erro"][solido="true"] {{ background: {c["erro"]}; color: {c["superficie"]}; }}

/* ---------- estrutura: barra lateral e cabeçalho ---------- */
QWidget#BarraLateral {{
    background: {c["superficie_lateral"]};
    border-right: 1px solid {c["borda"]};
}}
QWidget#Cabecalho {{
    background: {c["superficie_lateral"]};
    border-bottom: 1px solid {c["borda"]};
}}
QFrame#Divisoria {{ background: {c["borda"]}; border: none; max-height: 1px; min-height: 1px; }}
QFrame#DivisoriaVertical {{ background: {c["borda"]}; border: none; max-width: 1px; min-width: 1px; }}

QPushButton#ItemNav {{
    text-align: left;
    border: none;
    border-radius: {r["sm"]}px;
    padding: 0 {e["sm"]}px 0 {e["md"]}px;
    min-height: {d["altura_item_nav"]}px;
    max-height: {d["altura_item_nav"]}px;
    color: {c["texto_secundario"]};
    background: transparent;
    font-weight: {f["peso_medio"]};
}}
QPushButton#ItemNav:hover {{ background: {c["hover"]}; color: {c["texto"]}; }}
QPushButton#ItemNav:checked {{ background: {c["primaria_suave"]}; color: {c["primaria_texto"]}; font-weight: {f["peso_semi"]}; }}
QPushButton#ItemNav:focus {{ border: {d["borda_foco"]}px solid {c["foco"]}; padding-left: {e["md"] - d["borda_foco"]}px; }}
QPushButton#ItemNav:disabled {{ color: {c["texto_desabilitado"]}; }}

/* ---------- usuário no cabeçalho (MenuUsuario + PainelUsuario) ---------- */
QPushButton#MenuUsuario {{
    border: 1px solid transparent; border-radius: {r["md"]}px; background: transparent; padding: 0px;
}}
QPushButton#MenuUsuario:hover {{ background: {c["hover"]}; }}
QPushButton#MenuUsuario:focus {{ border: {d["borda_foco"]}px solid {c["foco"]}; }}
QLabel[peso="semi"] {{ font-weight: {f["peso_semi"]}; }}
QFrame#PainelUsuario {{
    background: {c["superficie_elevada"]}; border: 1px solid {c["borda"]}; border-radius: {r["md"]}px;
}}
QPushButton#ItemMenuUsuario {{
    text-align: left; border: 1px solid transparent; border-radius: {r["sm"]}px; background: transparent;
    color: {c["texto"]}; padding: {e["xs"] + 2}px {e["md"]}px;
}}
QPushButton#ItemMenuUsuario:hover {{ background: {c["hover"]}; }}
QPushButton#ItemMenuUsuario:focus {{ border: {d["borda_foco"]}px solid {c["foco"]}; }}
QPushButton#ItemMenuUsuario[perigo="true"] {{ color: {c["erro"]}; }}
QPushButton#ItemMenuUsuario[perigo="true"]:hover {{ background: {c["erro_suave"]}; }}

QPushButton#CabecalhoSecao {{
    text-align: left;
    border: none;
    border-radius: {r["sm"]}px;
    padding: 0 {e["xs"]}px;
    min-height: {d["alvo_minimo"]}px;
    max-height: {d["alvo_minimo"]}px;
    background: transparent;
    color: {c["texto_terciario"]};
    font-size: {f["legenda"]}px;
    font-weight: {f["peso_semi"]};
    letter-spacing: 0.4px;
}}
QPushButton#CabecalhoSecao:hover {{ color: {c["texto"]}; }}
QPushButton#CabecalhoSecao:focus {{ border: {d["borda_foco"]}px solid {c["foco"]}; }}

/* ---------- cartões ---------- */
QFrame[papel="cartao"] {{
    background: {c["superficie"]};
    border: 1px solid {c["borda"]};
    border-radius: {r["md"]}px;
}}
QFrame[papel="cartao"] QLabel {{ background: transparent; border: none; }}
QFrame[papel="placa_marca"] {{
    background: {tokens.MARCA["placa"]};
    border: 1px solid {c["borda"]};
    border-radius: {r["md"]}px;
}}
QFrame[papel="faixa"] {{ border-radius: {r["sm"]}px; border: 1px solid transparent; }}
QFrame[papel="faixa"][tom="info"] {{ background: {c["info_suave"]}; border-color: {c["info_suave"]}; }}
QFrame[papel="faixa"][tom="sucesso"] {{ background: {c["sucesso_suave"]}; border-color: {c["sucesso_suave"]}; }}
QFrame[papel="faixa"][tom="alerta"] {{ background: {c["alerta_suave"]}; border-color: {c["alerta_suave"]}; }}
QFrame[papel="faixa"][tom="erro"] {{ background: {c["erro_suave"]}; border-color: {c["erro_suave"]}; }}
QFrame[papel="faixa"][tom="neutro"] {{ background: {c["neutro_suave"]}; border-color: {c["neutro_suave"]}; }}
QFrame[papel="faixa"] QLabel {{ background: transparent; }}
QFrame[papel="faixa"][tom="info"] QLabel {{ color: {c["info"]}; }}
QFrame[papel="faixa"][tom="sucesso"] QLabel {{ color: {c["sucesso"]}; }}
QFrame[papel="faixa"][tom="alerta"] QLabel {{ color: {c["alerta"]}; }}
QFrame[papel="faixa"][tom="erro"] QLabel {{ color: {c["erro"]}; }}
QFrame[papel="faixa"][tom="neutro"] QLabel {{ color: {c["neutro"]}; }}

/* ---------- botões ---------- */
QPushButton {{
    min-height: {h - 2}px;
    padding: 0 {e["md"]}px;
    border-radius: {r["sm"]}px;
    border: 1px solid {c["borda_controle"]};
    background: {c["superficie"]};
    color: {c["texto"]};
    font-weight: {f["peso_medio"]};
}}
QPushButton:hover {{ background: {c["hover"]}; }}
QPushButton:pressed {{ background: {c["borda"]}; }}
QPushButton:focus {{ border: {d["borda_foco"]}px solid {c["foco"]}; padding: 0 {e["md"] - 1}px; }}
QPushButton:disabled {{ color: {c["texto_desabilitado"]}; border-color: {c["borda"]}; background: {c["superficie_alt"]}; }}

QPushButton[variante="primaria"] {{
    background: {c["primaria"]}; border: 1px solid {c["primaria"]}; color: {c["texto_sobre_primaria"]};
}}
QPushButton[variante="primaria"]:hover {{ background: {c["primaria_hover"]}; border-color: {c["primaria_hover"]}; }}
QPushButton[variante="primaria"]:pressed {{ background: {c["primaria_pressionada"]}; }}
QPushButton[variante="primaria"]:focus {{ border: {d["borda_foco"]}px solid {c["texto"]}; }}
QPushButton[variante="primaria"]:disabled {{
    background: {c["neutro_suave"]}; border-color: {c["neutro_suave"]}; color: {c["texto_desabilitado"]};
}}

QPushButton[variante="perigo"] {{ background: {c["erro"]}; border: 1px solid {c["erro"]}; color: {c["superficie"]}; }}
QPushButton[variante="perigo"]:hover {{ background: {c["erro_hover"]}; border-color: {c["erro_hover"]}; }}
QPushButton[variante="perigo"]:focus {{ border: {d["borda_foco"]}px solid {c["texto"]}; }}

QPushButton[variante="fantasma"] {{ border: 1px solid transparent; background: transparent; color: {c["texto_secundario"]}; }}
QPushButton[variante="fantasma"]:hover {{ background: {c["hover"]}; color: {c["texto"]}; }}
QPushButton[variante="fantasma"]:focus {{ border: {d["borda_foco"]}px solid {c["foco"]}; }}

QPushButton[variante="link"] {{ border: none; background: transparent; color: {c["primaria_texto"]}; padding: 0 {e["xs"]}px; }}
QPushButton[variante="link"]:hover {{ text-decoration: underline; }}
QPushButton[variante="link"]:focus {{ border: {d["borda_foco"]}px solid {c["foco"]}; }}

QPushButton[grande="true"] {{ min-height: {d["altura_controle_grande"] - 2}px; font-size: {f["subtitulo"] - 1}px; }}

QToolButton {{
    border: 1px solid transparent; border-radius: {r["sm"]}px; padding: {e["xs"]}px;
    min-width: {d["alvo_minimo"]}px; min-height: {d["alvo_minimo"]}px; background: transparent;
}}
QToolButton:hover {{ background: {c["hover"]}; }}
QToolButton:checked {{ background: {c["primaria_suave"]}; }}
QToolButton:focus {{ border: {d["borda_foco"]}px solid {c["foco"]}; }}
QToolButton[papel="botao_mapa"] {{
    background: {c["superficie"]}; border: 1px solid {c["borda_controle"]}; color: {c["texto"]};
    min-width: 0px; min-height: 0px; padding: 0px; font-weight: 600;
}}
QToolButton[papel="botao_mapa"]:hover {{ background: {c["hover"]}; }}

QLineEdit QToolButton {{ padding: 0; border: none; min-width: 0; min-height: 0; background: transparent; }}

/* ---------- campos ---------- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QDateTimeEdit {{
    min-height: {h - 2}px;
    max-height: {h - 2}px;
    padding: 0 {e["sm"]}px;
    border: 1px solid {c["borda_controle"]};
    border-radius: {r["sm"]}px;
    background: {c["superficie"]};
    color: {c["texto"]};
}}
QLineEdit[grande="true"] {{ min-height: {d["altura_controle_grande"] - 2}px; max-height: {d["altura_controle_grande"] - 2}px; padding: 0 {e["md"]}px; font-size: {f["subtitulo"] - 1}px; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover, QDateTimeEdit:hover {{
    border-color: {c["borda_forte"]};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QDateTimeEdit:focus {{
    border: {d["borda_foco"]}px solid {c["foco"]};
    padding: 0 {e["sm"] - 1}px;
}}
QLineEdit[grande="true"]:focus {{ padding: 0 {e["md"] - 1}px; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled {{
    background: {c["superficie_alt"]}; color: {c["texto_desabilitado"]}; border-color: {c["borda"]};
}}
QLineEdit[invalido="true"], QComboBox[invalido="true"] {{ border: {d["borda_foco"]}px solid {c["erro"]}; padding: 0 {e["sm"] - 1}px; }}
QLineEdit[busca="true"] {{ padding-left: {e["xs"]}px; }}
QPlainTextEdit, QTextEdit {{
    padding: {e["xs"]}px {e["xs"]}px;
    border: 1px solid {c["borda_controle"]};
    border-radius: {r["sm"]}px;
    background: {c["superficie"]};
    color: {c["texto"]};
}}
QPlainTextEdit:hover, QTextEdit:hover {{ border-color: {c["borda_forte"]}; }}
QPlainTextEdit:focus, QTextEdit:focus {{ border: {d["borda_foco"]}px solid {c["foco"]}; padding: {e["xs"] - 1}px; }}
/* texto de leitura (Central de ajuda): moldura de cartão, não de campo */
QTextBrowser[papel="leitor"], QTextBrowser[papel="leitor"]:hover, QTextBrowser[papel="leitor"]:focus {{
    border: 1px solid {c["borda"]}; border-radius: {r["md"]}px; padding: 0px; background: {c["superficie"]};
}}
QComboBox::drop-down, QDateEdit::drop-down, QDateTimeEdit::drop-down {{
    border: none; width: {e["xl"]}px; subcontrol-position: center right;
}}
QComboBox::down-arrow, QDateEdit::down-arrow, QDateTimeEdit::down-arrow {{ {seta} width: {d["icone"]}px; height: {d["icone"]}px; }}
QComboBox::down-arrow:disabled, QDateEdit::down-arrow:disabled {{ {seta_d} }}
QCalendarWidget QWidget {{ alternate-background-color: {c["superficie_alt"]}; }}
QCalendarWidget QToolButton {{ color: {c["texto"]}; font-weight: {f["peso_semi"]}; }}
QCalendarWidget QAbstractItemView {{
    background: {c["superficie_elevada"]}; selection-background-color: {c["primaria"]};
    selection-color: {c["texto_sobre_primaria"]}; border: none;
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {c["superficie_alt"]}; }}
QComboBox QAbstractItemView {{
    background: {c["superficie_elevada"]}; border: 1px solid {c["borda"]}; border-radius: {r["sm"]}px;
    padding: {e["xs"]}px; outline: 0;
}}
QComboBox QAbstractItemView::item {{ min-height: {d["altura_linha_tabela"]}px; padding: 0 {e["sm"]}px; border-radius: {r["sm"]}px; }}
QComboBox QAbstractItemView::item:hover {{ background: {c["hover"]}; }}
QComboBox QAbstractItemView::item:selected {{ background: {c["primaria_suave"]}; color: {c["primaria_texto"]}; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}

QCheckBox {{ spacing: {e["sm"]}px; min-height: {d["alvo_minimo"]}px; }}
QCheckBox::indicator {{
    width: {d["icone"]}px; height: {d["icone"]}px; border-radius: 3px;
    border: 1px solid {c["borda_controle"]}; background: {c["superficie"]};
}}
QCheckBox::indicator:hover {{ border-color: {c["borda_forte"]}; }}
QCheckBox::indicator:checked {{ background: {c["primaria"]}; border-color: {c["primaria"]}; {marca} }}
QCheckBox:focus {{ color: {c["primaria_texto"]}; }}
QCheckBox::indicator:focus {{ border: {d["borda_foco"]}px solid {c["foco"]}; }}

/* ---------- tabelas ---------- */
QTableView, QTreeView, QListView {{
    background: {c["superficie"]};
    alternate-background-color: {c["superficie_alt"]};
    border: 1px solid {c["borda"]};
    border-radius: {r["md"]}px;
    gridline-color: {c["borda"]};
    selection-background-color: {c["selecao"]};
    selection-color: {c["texto"]};
}}
QTableView:focus, QTreeView:focus, QListView:focus {{ border: 1px solid {c["foco"]}; }}
QTreeWidget#ListaAjuda {{ padding: {e["xs"]}px; outline: 0; }}
QTreeWidget#ListaAjuda::item {{ padding: {e["xs"] + 1}px {e["sm"]}px; border-radius: {r["sm"]}px; }}
QTreeWidget#ListaAjuda::item:hover {{ background: {c["hover"]}; }}
QTreeWidget#ListaAjuda::item:selected {{ background: {c["primaria_suave"]}; color: {c["primaria_texto"]}; }}
QTableView[embutida="true"] {{ border: none; border-top: 1px solid {c["borda"]}; border-radius: 0; }}
QTableView[embutida="true"]:focus {{ border: none; border-top: 1px solid {c["foco"]}; }}
QTableView::item {{ padding: 0 {e["sm"]}px; border: none; }}
QTableView::item:hover {{ background: {c["hover"]}; }}
QTableView::item:selected {{ background: {c["selecao"]}; color: {c["texto"]}; }}
QHeaderView {{ background: transparent; border: none; }}
QHeaderView::section {{
    background: {c["superficie_alt"]};
    color: {c["texto_secundario"]};
    font-weight: {f["peso_semi"]};
    font-size: {f["pequeno"]}px;
    border: none;
    border-bottom: 1px solid {c["borda"]};
    padding: 0 {e["sm"]}px;
    min-height: {d["altura_linha_tabela"]}px;
}}
QHeaderView::section:hover {{ color: {c["texto"]}; }}
QTableCornerButton::section {{ background: {c["superficie_alt"]}; border: none; }}

/* ---------- abas ---------- */
QTabWidget::pane {{ border: none; }}
QTabBar {{ qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent; color: {c["texto_secundario"]};
    padding: 0 {e["md"]}px; min-height: {h}px;
    border: none; border-bottom: 2px solid transparent; margin-right: {e["xs"]}px;
    font-weight: {f["peso_medio"]};
}}
QTabBar::tab:hover {{ color: {c["texto"]}; }}
QTabBar::tab:selected {{ color: {c["primaria_texto"]}; border-bottom-color: {c["primaria"]}; }}
QTabBar::tab:focus {{ border: {d["borda_foco"]}px solid {c["foco"]}; }}
QTabBar::tab:disabled {{ color: {c["borda"]}; padding: 0 {e["xxs"]}px; margin-right: {e["xs"]}px; }}

/* ---------- progresso ---------- */
QProgressBar {{
    border: none; border-radius: {r["sm"]}px; background: {c["neutro_suave"]};
    max-height: 8px; min-height: 8px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {c["primaria"]}; border-radius: {r["sm"]}px; }}
QProgressBar[estado="sucesso"]::chunk {{ background: {c["sucesso"]}; }}
QProgressBar[estado="erro"]::chunk {{ background: {c["erro"]}; }}

/* ---------- rolagem ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {c["borda"]}; border-radius: 3px; min-height: 32px; min-width: 32px; }}
QScrollBar::handle:hover {{ background: {c["borda_controle"]}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------- menus, dicas ---------- */
QMenu {{
    background: {c["superficie_elevada"]}; border: 1px solid {c["borda"]}; border-radius: {r["md"]}px;
    padding: {e["xs"]}px;
}}
QMenu::item {{ padding: {e["xs"] + 2}px {e["lg"]}px {e["xs"] + 2}px {e["md"]}px; border-radius: {r["sm"]}px; }}
QMenu::item:selected {{ background: {c["hover"]}; }}
QMenu::separator {{ height: 1px; background: {c["borda"]}; margin: {e["xs"]}px {e["sm"]}px; }}
QToolTip {{
    background: {c["superficie_elevada"]}; color: {c["texto"]};
    border: 1px solid {c["borda"]}; border-radius: {r["sm"]}px; padding: {e["xs"]}px {e["sm"]}px;
}}

/* ---------- barra de ferramentas do matplotlib ---------- */
QToolBar#BarraGrafico {{ background: transparent; border: none; spacing: {e["xxs"]}px; padding: 0; }}
QToolBar#BarraGrafico QToolButton {{ min-width: 28px; min-height: 28px; }}
QToolBar#BarraGrafico QLabel {{ color: {c["texto_terciario"]}; font-family: {mono}; font-size: {f["pequeno"]}px; }}
"""


if __name__ == "__main__":
    pasta = Path(__file__).resolve().parent
    for modo in tokens.MODOS:
        (pasta / f"tema-{modo}.qss").write_text(gerar_qss(modo), encoding="utf-8")
        print(f"gravado tema/tema-{modo}.qss")
