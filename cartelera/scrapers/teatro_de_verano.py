"""Teatro de Verano (MVD CMS de la Intendencia). Pocos espectáculos, pero clave en verano y en Carnaval."""

import html
import re
from datetime import datetime, timedelta

from cartelera.categorias import clasificar, esta_cancelado
from cartelera.extraer import meta, recortar
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, LugarCrudo
from cartelera.scrapers.mvd_cms import funciones_de_texto

NOMBRE = "teatro_de_verano"
BASE = "https://teatrodeverano.montevideo.gub.uy"
LUGAR = LugarCrudo(nombre="Teatro de Verano Ramón Collazo", direccion="Rambla Wilson s/n, Parque Rodó")
_TARJETA = re.compile(
    r'<section class="img-item">.*?<img src="([^"]+)".*?<a href="([^"]+-uc(\d+))"[^>]*>([^<]+)</a>\s*</h2>\s*<p class="text[^"]*">([^<]*)</p>',
    re.S,
)
_COMPRA = re.compile(r'href="(https?://(?:www\.)?(?:tickantel\.com\.uy|redtickets\.uy|www\.redtickets\.uy|abitab\.com\.uy)[^"]*)"')


def leer_programacion(pagina: str) -> list[dict]:
    return [
        {"imagen": imagen, "url": url, "id": id_, "titulo": html.unescape(titulo).strip(), "fecha": fecha}
        for imagen, url, id_, titulo, fecha in _TARJETA.findall(pagina)
    ]


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for tarjeta in leer_programacion(cliente.texto(f"{BASE}/categoria/Programacion-2")):
        if esta_cancelado(tarjeta["titulo"]):
            continue
        funciones = [
            f for f in funciones_de_texto(tarjeta["fecha"], ahora.date(), ahora.tzinfo)
            if (f.inicio.date() >= ahora.date() if f.sin_hora else f.inicio >= ahora - timedelta(hours=6))
        ]
        if not funciones:  # por ejemplo, "Prueba de admisión", sin fecha de espectáculo
            continue
        try:
            detalle = cliente.texto(tarjeta["url"])
        except Exception as error:  # noqa: BLE001
            errores.append(f"{tarjeta['url']}: {type(error).__name__}: {error}")
            continue
        compra = _COMPRA.search(detalle)
        compra = compra.group(1) if compra else None
        descripcion = meta(detalle, "og:description") or meta(detalle, "description")
        eventos.append(EventoCrudo(
            fuente=NOMBRE,
            id_externo=tarjeta["id"],
            url=tarjeta["url"],
            titulo=tarjeta["titulo"],
            categoria=clasificar(tarjeta["titulo"], descripcion, por_defecto="musica"),
            descripcion_corta=recortar(descripcion),
            lugar=LUGAR,
            funciones=funciones,
            entradas=[Entrada(url=compra, via="tickantel" if "tickantel" in compra else "redtickets" if "redtickets" in compra else "abitab")] if compra else [],
            imagen_url=tarjeta["imagen"],
            productor="Teatro de Verano",
            enlaces=[compra] if compra else [],
        ))
    return eventos, errores
