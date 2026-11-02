"""
Mapa para escolher um ponto (latitude/longitude), desenhado com o Qt a partir
dos ladrilhos (tiles) do OpenStreetMap — sem navegador embutido.

    mapa = MapaSeletor()
    mapa.definir_posicao(-29.72, -53.72)          # marcador e centro (None, None = sem marcador)
    mapa.posicao_escolhida.connect(lambda lat, lon: ...)   # clique no mapa

Arrastar move o mapa; roda do mouse ou os botões + e − mudam o zoom; um clique
(sem arrastar) põe o marcador. Os ladrilhos ficam em cache no disco. Sem
internet, o mapa mostra um aviso e quem usa continua com os campos de texto.

Uso dos ladrilhos do OpenStreetMap: identificação no User-Agent, cache e o
crédito "© OpenStreetMap contributors" sempre visível
(https://operations.osmfoundation.org/policies/tiles/).
"""

from __future__ import annotations

import math
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from ..tema import ESPACO, cor, gerenciador
from ..tema.marca import marca_atual

TAMANHO_LADRILHO = 256
ZOOM_MIN, ZOOM_MAX = 2, 18
URL_LADRILHO = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
CREDITO = "© OpenStreetMap contributors"
MAX_LADRILHOS_MEMORIA = 400


def para_pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Latitude/longitude → pixel no mapa inteiro (projeção Web Mercator)."""
    n = TAMANHO_LADRILHO * 2 ** zoom
    lat = max(-85.0511, min(85.0511, lat))
    x = (lon + 180.0) / 360.0 * n
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def para_geo(x: float, y: float, zoom: int) -> tuple[float, float]:
    """Pixel no mapa inteiro → latitude/longitude."""
    n = TAMANHO_LADRILHO * 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, ((lon + 180.0) % 360.0) - 180.0


class MapaSeletor(QWidget):
    """Mapa com marcador. `posicao_escolhida(lat, lon)` é emitido no clique."""

    posicao_escolhida = Signal(float, float)

    def __init__(self, zoom: int = 12, carregar_ladrilhos: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.setMouseTracking(False)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAccessibleName("Mapa para escolher a posição")
        self.setToolTip("Clique para marcar a posição · arraste para mover · roda do mouse para zoom")
        self.zoom = zoom
        padrao = marca_atual().posicao_padrao_mapa
        self._centro = para_pixel(*padrao, zoom)       # pixel do centro da vista, no zoom atual
        self.marcador: tuple[float, float] | None = None
        self._ladrilhos: OrderedDict[tuple[int, int, int], QPixmap] = OrderedDict()
        self._pendentes: set[tuple[int, int, int]] = set()
        self._falhas = 0
        self._sucessos = 0
        self._arrasto_inicio: QPointF | None = None
        self._arrastou = False
        self._rede = None
        if carregar_ladrilhos:
            self._rede = QNetworkAccessManager(self)
            cache = QNetworkDiskCache(self)
            pasta = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)) / "mapa"
            cache.setCacheDirectory(str(pasta))
            cache.setMaximumCacheSize(200 * 1024 * 1024)
            self._rede.setCache(cache)
            self._rede.finished.connect(self._ladrilho_chegou)
        self._montar_botoes()
        # método (e não lambda): o Qt desconecta sozinho quando o mapa é destruído
        gerenciador().tema_alterado.connect(self._tema_alterado)

    def _tema_alterado(self, *_):
        self.update()

    # ------------------------------------------------------------ API
    def definir_posicao(self, lat: float | None, lon: float | None, centralizar: bool = True) -> None:
        """Põe o marcador (ou tira, com None) e, se pedido, centraliza nele."""
        if lat is None or lon is None:
            self.marcador = None
        else:
            self.marcador = (float(lat), float(lon))
            if centralizar:
                self._centro = para_pixel(lat, lon, self.zoom)
        self.update()

    def centro(self) -> tuple[float, float]:
        return para_geo(*self._centro, self.zoom)

    def mudar_zoom(self, passo: int, em: QPointF | None = None) -> None:
        """Zoom de `passo` níveis mantendo fixo o ponto `em` da tela (padrão: o centro)."""
        novo = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom + passo))
        if novo == self.zoom:
            return
        em = em if em is not None else QPointF(self.width() / 2, self.height() / 2)
        geo = self._geo_da_tela(em)
        self.zoom = novo
        x, y = para_pixel(*geo, novo)
        self._centro = (x - (em.x() - self.width() / 2), y - (em.y() - self.height() / 2))
        self._limitar_centro()
        self.update()

    # ------------------------------------------------------------ conversões
    def _origem(self) -> tuple[float, float]:
        return self._centro[0] - self.width() / 2, self._centro[1] - self.height() / 2

    def _geo_da_tela(self, ponto: QPointF) -> tuple[float, float]:
        ox, oy = self._origem()
        return para_geo(ox + ponto.x(), oy + ponto.y(), self.zoom)

    def _tela_do_geo(self, lat: float, lon: float) -> QPointF:
        x, y = para_pixel(lat, lon, self.zoom)
        ox, oy = self._origem()
        return QPointF(x - ox, y - oy)

    def _limitar_centro(self) -> None:
        n = TAMANHO_LADRILHO * 2 ** self.zoom
        self._centro = (self._centro[0] % n, max(0.0, min(float(n), self._centro[1])))

    # ------------------------------------------------------------ ladrilhos
    def _pedir(self, chave: tuple[int, int, int]) -> None:
        if self._rede is None or chave in self._pendentes:
            return
        z, x, y = chave
        pedido = QNetworkRequest(QUrl(URL_LADRILHO.format(z=z, x=x, y=y)))
        m = marca_atual()
        pedido.setRawHeader(b"User-Agent", f"{m.nome_app}/1 (app desktop do {m.laboratorio}, "
                                           f"{m.instituicao_sigla})".encode())
        pedido.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute,
                            QNetworkRequest.CacheLoadControl.PreferCache)
        resposta = self._rede.get(pedido)
        resposta.setProperty("chave", chave)
        self._pendentes.add(chave)

    def _ladrilho_chegou(self, resposta: QNetworkReply) -> None:
        chave = tuple(resposta.property("chave") or ())
        self._pendentes.discard(chave)
        if resposta.error() == QNetworkReply.NetworkError.NoError:
            pixmap = QPixmap()
            if pixmap.loadFromData(resposta.readAll()):
                self._ladrilhos[chave] = pixmap
                self._sucessos += 1
                while len(self._ladrilhos) > MAX_LADRILHOS_MEMORIA:
                    self._ladrilhos.popitem(last=False)
        else:
            self._falhas += 1
        resposta.deleteLater()
        self.update()

    @property
    def sem_conexao(self) -> bool:
        """True se nenhum ladrilho carregou e algum pedido falhou (ou não há rede)."""
        return self._rede is None or (self._sucessos == 0 and self._falhas > 0)

    # ------------------------------------------------------------ desenho
    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        fundo = QColor(cor("superficie_alt"))
        p.fillRect(self.rect(), fundo)
        n_lad = 2 ** self.zoom
        ox, oy = self._origem()
        x0, y0 = int(math.floor(ox / TAMANHO_LADRILHO)), int(math.floor(oy / TAMANHO_LADRILHO))
        x1 = int(math.floor((ox + self.width()) / TAMANHO_LADRILHO))
        y1 = int(math.floor((oy + self.height()) / TAMANHO_LADRILHO))
        for ty in range(max(0, y0), min(n_lad - 1, y1) + 1):
            for tx in range(x0, x1 + 1):
                chave = (self.zoom, tx % n_lad, ty)
                destino = QRectF(tx * TAMANHO_LADRILHO - ox, ty * TAMANHO_LADRILHO - oy,
                                 TAMANHO_LADRILHO, TAMANHO_LADRILHO)
                pixmap = self._ladrilhos.get(chave)
                if pixmap is not None:
                    self._ladrilhos.move_to_end(chave)
                    p.drawPixmap(destino, pixmap, QRectF(pixmap.rect()))
                else:
                    self._pedir(chave)
        if self.marcador is not None:
            self._desenhar_marcador(p, self._tela_do_geo(*self.marcador))
        if self.sem_conexao:
            p.setPen(QColor(cor("texto_secundario")))
            p.drawText(self.rect().adjusted(ESPACO["md"], 0, -ESPACO["md"], 0),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       "Mapa indisponível sem internet.\nDigite as coordenadas nos campos acima.")
        self._desenhar_credito(p)
        p.setPen(QPen(QColor(cor("borda_controle")), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
        p.end()

    def _desenhar_marcador(self, p: QPainter, ponto: QPointF) -> None:
        raio = 7
        ponta = QPointF(ponto.x(), ponto.y())
        topo = QPointF(ponto.x(), ponto.y() - 3.2 * raio)
        caminho = QPainterPath()
        caminho.moveTo(ponta)
        caminho.quadTo(QPointF(ponto.x() - 1.6 * raio, ponto.y() - 1.8 * raio), QPointF(ponto.x() - raio, topo.y()))
        caminho.arcTo(QRectF(ponto.x() - raio, topo.y() - raio, 2 * raio, 2 * raio), 180, -180)
        caminho.quadTo(QPointF(ponto.x() + 1.6 * raio, ponto.y() - 1.8 * raio), ponta)
        p.setPen(QPen(QColor("#FFFFFF"), 2))
        p.setBrush(QColor(cor("primaria")))
        p.drawPath(caminho)
        p.setBrush(QColor("#FFFFFF"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(topo, raio * 0.4, raio * 0.4)

    def _desenhar_credito(self, p: QPainter) -> None:
        fonte = p.font()
        fonte.setPixelSize(10)
        p.setFont(fonte)
        largura = p.fontMetrics().horizontalAdvance(CREDITO) + 8
        caixa = QRectF(self.width() - largura - 1, self.height() - 16, largura, 15)
        p.fillRect(caixa, QColor(255, 255, 255, 200))
        p.setPen(QColor("#333333"))
        p.drawText(caixa, Qt.AlignmentFlag.AlignCenter, CREDITO)

    # ------------------------------------------------------------ interação
    def _montar_botoes(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(ESPACO["sm"], ESPACO["sm"], ESPACO["sm"], ESPACO["sm"])
        linha = QHBoxLayout()
        coluna = QVBoxLayout()
        coluna.setSpacing(2)
        for texto, passo, nome in (("+", 1, "Aproximar"), ("−", -1, "Afastar")):
            b = QToolButton()
            b.setText(texto)
            b.setFixedSize(30, 30)
            b.setToolTip(nome)
            b.setAccessibleName(nome)
            b.setProperty("papel", "botao_mapa")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, s=passo: self.mudar_zoom(s))
            coluna.addWidget(b)
        linha.addLayout(coluna)
        linha.addStretch(1)
        lay.addLayout(linha)
        lay.addStretch(1)

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton:
            self._arrasto_inicio = evento.position()
            self._arrastou = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, evento) -> None:
        if self._arrasto_inicio is None:
            return
        delta = evento.position() - self._arrasto_inicio
        if not self._arrastou and abs(delta.x()) + abs(delta.y()) < 4:
            return
        self._arrastou = True
        self._centro = (self._centro[0] - delta.x(), self._centro[1] - delta.y())
        self._limitar_centro()
        self._arrasto_inicio = evento.position()
        self.update()

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() != Qt.MouseButton.LeftButton or self._arrasto_inicio is None:
            return
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if not self._arrastou:
            lat, lon = self._geo_da_tela(evento.position())
            self.definir_posicao(lat, lon, centralizar=False)
            self.posicao_escolhida.emit(lat, lon)
        self._arrasto_inicio = None

    def wheelEvent(self, evento) -> None:
        passo = 1 if evento.angleDelta().y() > 0 else -1
        self.mudar_zoom(passo, evento.position())
