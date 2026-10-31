"""Museos de la Intendencia: exposiciones del Cabildo y del Subte (sitios Drupal 7 de la IM).

Los dos listan sus exposiciones como tarjetas con título, imagen y un resumen. El Cabildo pone el
período en el resumen ("Abril 2026 - Abril 2027") y lista también las pasadas, así que se toman las que
siguen abiertas. El Subte tiene una página solo con las actuales, sin fecha de cierre.

El Blanes y el Museo de las Migraciones usan la misma plataforma, pero mezclan exposiciones viejas,
convocatorias e inauguraciones sin fecha de cierre: no hay forma segura de saber qué está abierto.
"""

import html
import re
from datetime import datetime

from cartelera.categorias import esta_cancelado
from cartelera.extraer import recortar, texto_plano
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, LugarCrudo, Precio
from cartelera.scrapers.muestras import funciones_de_muestra, periodo_por_meses

NOMBRE = "museos_im"
MUSEOS = [
    {
        "sitio": "https://cabildo.montevideo.gub.uy", "listado": "/exposiciones", "solo_actuales": False,
        "lugar": LugarCrudo(nombre="Cabildo de Montevideo", direccion="Juan Carlos Gómez 1362", lat=-34.90653, lon=-56.20278),
    },
    {
        "sitio": "https://subte.montevideo.gub.uy", "listado": "/exposiciones/exposiciones", "solo_actuales": True,
        "lugar": LugarCrudo(nombre="Centro de Exposiciones Subte", direccion="Plaza Fabini", lat=-34.90563, lon=-56.19423),
    },
]
_TARJETA = re.compile(r'<div\s+about="(/[^"]+)"[^>]*class="[^"]*node-teaser[^"]*">(.*?)(?=<div\s+about="|</section>|<div class="view-footer|$)', re.S)


def leer_tarjetas(pagina: str) -> list[dict]:
    tarjetas = []
    for ruta, cuerpo in _TARJETA.findall(pagina):
        titulo = re.search(r"<h2><a [^>]*>(.*?)</a></h2>", cuerpo, re.S)
        resumen = re.search(r'field-name-field-resumen[^>]*>(.*?)</(?:p|div)>\s*(?:</div>\s*)*', cuerpo, re.S)
        imagen = re.search(r'<img[^>]+src="([^"]+)"', cuerpo)
        if titulo:
            tarjetas.append({
                "ruta": ruta,
                "titulo": texto_plano(titulo.group(1)),
                "resumen": texto_plano(resumen.group(1)) if resumen else "",
                "imagen": html.unescape(imagen.group(1)) if imagen else None,
            })
    return tarjetas


def armar_muestra(tarjeta: dict, museo: dict, ahora: datetime) -> EventoCrudo | None:
    titulo = tarjeta["titulo"]
    if not titulo or esta_cancelado(titulo) or re.search(r"(?i)\b(pasadas|anteriores|convocatoria)\b", f"{tarjeta['ruta']} {titulo}"):
        return None
    periodo = periodo_por_meses(tarjeta["resumen"])
    if museo["solo_actuales"]:
        desde, hasta = None, None
    elif periodo:
        desde, hasta = periodo
        if hasta < ahora.date():
            return None
    else:
        return None  # sin período no se sabe si sigue abierta
    funciones = funciones_de_muestra(desde, hasta, ahora)
    if not funciones:
        return None
    url = f"{museo['sitio']}{tarjeta['ruta']}"
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=url.split("//", 1)[1],
        url=url,
        titulo=titulo,
        categoria="exposicion",
        categoria_segura=True,
        descripcion_corta=recortar(tarjeta["resumen"]) if not periodo else None,
        lugar=museo["lugar"],
        funciones=funciones,
        precio=Precio(desde=0, hasta=0, gratis=True),  # los museos de la IM son de entrada libre
        entradas=[Entrada(url=url, via=NOMBRE)],
        imagen_url=tarjeta["imagen"],
        productor="Intendencia de Montevideo",
        muestra=True,
        hasta=hasta,
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for museo in MUSEOS:
        try:
            tarjetas = leer_tarjetas(cliente.texto(f"{museo['sitio']}{museo['listado']}"))
        except Exception as error:  # noqa: BLE001 - un museo caído no frena al otro
            errores.append(f"{museo['sitio']}: {type(error).__name__}: {error}")
            continue
        for tarjeta in tarjetas:
            if evento := armar_muestra(tarjeta, museo, ahora):
                eventos.append(evento)
    return eventos, errores
