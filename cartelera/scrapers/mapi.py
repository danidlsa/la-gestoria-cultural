"""MAPI (Museo de Arte Precolombino e Indígena): exposiciones actuales de su página de exposiciones.

Es un WordPress con un constructor visual: cada exposición es una tarjeta marcada con su estado
("exposicion-actual"). No informa la fecha de cierre, así que se toma como abierta mientras siga marcada.
"""

import html
import re
from datetime import datetime

from cartelera.categorias import esta_cancelado
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, LugarCrudo
from cartelera.scrapers.muestras import funciones_de_muestra

NOMBRE = "mapi"
BASE = "https://mapi.uy"
LUGAR = LugarCrudo(nombre="Museo de Arte Precolombino e Indígena (MAPI)", direccion="25 de Mayo 279", lat=-34.90715, lon=-56.21011)
_ACTUAL = re.compile(r'estado_de_exposicion-exposicion-actual[^"]*" data-link-url="([^"]+)"(.*?)(?=swiper-slide|$)', re.S)


def actuales(pagina: str) -> list[dict]:
    """Exposiciones actuales, sin repetir (el carrusel repite tarjetas)."""
    vistas = {}
    for url, cuerpo in _ACTUAL.findall(pagina):
        imagen = re.search(r'<img[^>]+data-src="([^"]+)"[^>]+alt="([^"]*)"', cuerpo)
        if imagen and url not in vistas:
            vistas[url] = {"url": html.unescape(url), "imagen": imagen.group(1), "titulo": html.unescape(imagen.group(2)).strip()}
    return list(vistas.values())


def armar_muestra(item: dict, ahora: datetime) -> EventoCrudo | None:
    if not item["titulo"] or esta_cancelado(item["titulo"]):
        return None
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=item["url"].rstrip("/").rsplit("/", 1)[-1],
        url=item["url"],
        titulo=item["titulo"],
        categoria="exposicion",
        categoria_segura=True,
        lugar=LUGAR,
        funciones=funciones_de_muestra(None, None, ahora),
        entradas=[Entrada(url=item["url"], via=NOMBRE)],
        imagen_url=item["imagen"],
        productor="MAPI",
        muestra=True,
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos = [e for item in actuales(cliente.texto(f"{BASE}/pagina-exposiciones/")) if (e := armar_muestra(item, ahora))]
    return eventos, []
