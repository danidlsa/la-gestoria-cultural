"""Cliente HTTP compartido: User-Agent propio, robots.txt, pausas y reintentos."""

import logging
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "CarteleraMVD/0.1 (+https://github.com/danidlsa/cartelera-cultural)"
log = logging.getLogger(__name__)


class BloqueadoPorRobots(Exception):
    pass


class Cliente:
    """Hace pedidos GET respetando robots.txt y una pausa mínima entre pedidos al mismo sitio."""

    def __init__(self, pausa: float = 1.0, reintentos: int = 2, timeout: float = 25.0):
        self.pausa = pausa
        self.reintentos = reintentos
        self._http = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept-Language": "es-UY,es;q=0.9"},
            timeout=timeout,
            follow_redirects=True,
        )
        self._robots: dict[str, RobotFileParser | None] = {}
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
                    parser = RobotFileParser()
                    parser.parse(respuesta.text.splitlines())
            except httpx.HTTPError:
                pass  # Sin robots.txt accesible, se asume permitido.
            self._robots[sitio] = parser
        parser = self._robots[sitio]
        return parser is None or parser.can_fetch(USER_AGENT, url)

    def _esperar_turno(self, url: str) -> None:
        host = urlsplit(url).netloc
        espera = self._ultimo_pedido.get(host, 0) + self.pausa - time.monotonic()
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
