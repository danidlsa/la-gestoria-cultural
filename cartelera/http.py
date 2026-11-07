"""Cliente HTTP compartido: User-Agent propio, robots.txt, pausas y reintentos."""

import logging
import re
import time
from urllib.parse import unquote, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "CarteleraMVD/0.1 (+https://github.com/danidlsa/la-gestoria-cultural)"
log = logging.getLogger(__name__)


class BloqueadoPorRobots(Exception):
    pass


class Robots(RobotFileParser):
    """robots.txt leído como dice el estándar (RFC 9309) y como lo leen Google y Bing.

    El de Python toma la primera regla que coincide y no entiende `*` ni `$`. El estándar manda usar la regla
    más larga (la más específica) y, si empatan, la que permite. Con el de Python, en google.com un
    "Disallow: /maps/" bloqueaba lo que un "Allow: /maps/d/" más abajo permite.
    """

    @staticmethod
    def _patron(regla: str) -> re.Pattern:
        fin = regla.endswith("$")
        cuerpo = re.escape(regla[:-1] if fin else regla).replace(r"\*", ".*")
        return re.compile(cuerpo + ("$" if fin else ""))

    def can_fetch(self, useragent: str, url: str) -> bool:
        if self.disallow_all:
            return False
        if self.allow_all or not self.last_checked:
            return super().can_fetch(useragent, url)
        partes = urlsplit(url)
        ruta = unquote(partes.path or "/") + (f"?{unquote(partes.query)}" if partes.query else "")
        grupo = next((e for e in self.entries if e.applies_to(useragent)), self.default_entry)
        if grupo is None:
            return True
        mejor, permite = -1, True
        for linea in grupo.rulelines:
            regla = unquote(linea.path)
            if not regla:  # "Disallow:" vacío no bloquea nada
                continue
            if self._patron(regla).match(ruta) and (len(regla) > mejor or (len(regla) == mejor and linea.allowance)):
                mejor, permite = len(regla), linea.allowance
        return permite


class Cliente:
    """Hace pedidos respetando robots.txt y una pausa entre pedidos al mismo sitio (como mínimo, su Crawl-delay)."""

    def __init__(self, pausa: float = 1.0, reintentos: int = 2, timeout: float = 25.0):
        self.pausa = pausa
        self.reintentos = reintentos
        self._http = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "es-UY,es;q=0.9"},
            timeout=timeout,
            follow_redirects=True,
        )
        self._robots: dict[str, Robots | None] = {}
        self._ultimo_pedido: dict[str, float] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._http.close()

    def _permitido(self, url: str) -> bool:
        partes = urlsplit(url)
        sitio = f"{partes.scheme}://{partes.netloc}"
        if sitio not in self._robots:
            parser = None
            try:
                respuesta = self._http.get(f"{sitio}/robots.txt")
                if respuesta.status_code == 200:
                    parser = Robots()
                    parser.parse(respuesta.text.splitlines())
            except httpx.HTTPError:
                pass  # Sin robots.txt accesible, se asume permitido.
            self._robots[sitio] = parser
        parser = self._robots[sitio]
        return parser is None or parser.can_fetch(USER_AGENT, url)

    def _pausa_de(self, url: str) -> float:
        """La pausa entre pedidos al sitio: la nuestra o la que pide su robots.txt (Crawl-delay), la mayor."""
        partes = urlsplit(url)
        parser = self._robots.get(f"{partes.scheme}://{partes.netloc}")
        pedida = parser.crawl_delay(USER_AGENT) if parser else None
        return max(self.pausa, float(pedida or 0))

    def _esperar_turno(self, url: str) -> None:
        host = urlsplit(url).netloc
        espera = self._ultimo_pedido.get(host, 0) + self._pausa_de(url) - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        self._ultimo_pedido[host] = time.monotonic()

    def get(self, url: str) -> httpx.Response:
        if not self._permitido(url):
            raise BloqueadoPorRobots(url)
        for intento in range(self.reintentos + 1):
            self._esperar_turno(url)
            try:
                respuesta = self._http.get(url)
                if respuesta.status_code < 500:
                    respuesta.raise_for_status()
                    return respuesta
                log.warning("HTTP %s en %s (intento %s)", respuesta.status_code, url, intento + 1)
            except httpx.TransportError as error:
                log.warning("%s en %s (intento %s)", type(error).__name__, url, intento + 1)
                if intento == self.reintentos:
                    raise
            time.sleep(2 * (intento + 1))
        respuesta.raise_for_status()
        return respuesta

    def texto(self, url: str) -> str:
        return self.get(url).text

    def post_json(self, url: str, datos: dict) -> dict:
        """POST con cuerpo JSON (por ejemplo, las llamadas JSON-RPC de los sitios hechos con Odoo)."""
        if not self._permitido(url):
            raise BloqueadoPorRobots(url)
        self._esperar_turno(url)
        respuesta = self._http.post(url, json=datos)
        respuesta.raise_for_status()
        return respuesta.json()
