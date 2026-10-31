"""Teatro Solís (MVD CMS). Suma la sala interna, el género y qué obras son de la Comedia Nacional."""

import re
from datetime import datetime, timedelta

from cartelera.http import Cliente
from cartelera.modelo import EventoCrudo, LugarCrudo
from cartelera.scrapers.mvd_cms import armar_evento, leer_listado

NOMBRE = "solis"
BASE = "https://www.teatrosolis.org.uy"
CATEGORIA_PROGRAMACION = 115
LUGAR = LugarCrudo(nombre="Teatro Solís", direccion="Buenos Aires s/n esq. Bartolomé Mitre", lat=-34.90786, lon=-56.20101)


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    desde, hasta = ahora.strftime("%Y%m%d"), (ahora + timedelta(days=200)).strftime("%Y%m%d")
    tarjetas = leer_listado(cliente.texto(f"{BASE}/acategoriaperiodo.aspx?{CATEGORIA_PROGRAMACION},{desde},{hasta},0"))

    # Las obras de la Comedia Nacional salen de las páginas de su categoría (una por temporada).
    portada = cliente.texto(f"{BASE}/home")
    comedia_nacional: set[str] = set()
    for url in set(re.findall(r'href="(https://www\.teatrosolis\.org\.uy/categoria/Comedia-Nacional-\d+)"', portada)):
        comedia_nacional.update(re.findall(r"-uc(\d+)\"", cliente.texto(url)))

    eventos, errores = [], []
    for tarjeta in tarjetas:
        try:
            productor = "Comedia Nacional" if tarjeta["id"] in comedia_nacional else "Teatro Solís"
            evento = armar_evento(tarjeta, NOMBRE, LUGAR, ahora, productor)
        except Exception as error:  # noqa: BLE001
            errores.append(f"{tarjeta['url']}: {type(error).__name__}: {error}")
            continue
        if evento:
            eventos.append(evento)
    return eventos, errores
