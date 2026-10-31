"""Museo Torres García: las exposiciones actuales de su página de exposiciones (HTML simple).

La página no informa fechas: lo que está en "Actuales" se toma como abierto mientras siga ahí.
"""

import re
from datetime import datetime

from cartelera.categorias import esta_cancelado
from cartelera.extraer import recortar, texto_plano
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, LugarCrudo
from cartelera.scrapers.muestras import funciones_de_muestra

NOMBRE = "torres_garcia"
BASE = "https://www.torresgarcia.org.uy"
LUGAR = LugarCrudo(nombre="Museo Torres García", direccion="Sarandí 683", lat=-34.90646, lon=-56.20138)
_ITEM = re.compile(r"<div class='item_exposiciones'>(.*?)<a href=\"(exposiciones/[^\"]+)\"", re.S)


def actuales(pagina: str) -> list[dict]:
    """Las exposiciones entre el título "Actuales" y el de las pasadas."""
    inicio = pagina.find(">Actuales<")
    fin = pagina.find("PASADAS", inicio)
    bloque = pagina[inicio:fin if fin > 0 else None] if inicio >= 0 else ""
    items = []
    for cuerpo, ruta in _ITEM.findall(bloque):
        autor = re.search(r"content_expo_autor'>\s*<p[^>]*>(.*?)</p>", cuerpo, re.S)
        titulo = re.search(r"content_expo_titulo'>\s*<p[^>]*>(.*?)</p>", cuerpo, re.S)
        detalle = re.search(r"content_expo_detalle'>(.*)", cuerpo, re.S)
        items.append({
            "ruta": ruta,
            "nombre": texto_plano(autor.group(1)) if autor else "",
            "autor": texto_plano(titulo.group(1)) if titulo else "",
            "detalle": texto_plano(detalle.group(1)) if detalle else "",
        })
    return items


def armar_muestra(item: dict, ahora: datetime) -> EventoCrudo | None:
    titulo = " - ".join(p for p in (item["nombre"], item["autor"].title() if item["autor"].isupper() else item["autor"]) if p)
    if not titulo or esta_cancelado(titulo):
        return None
    url = f"{BASE}/{item['ruta']}"
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=item["ruta"].strip("/").rsplit("/", 1)[-1],
        url=url,
        titulo=titulo,
        categoria="exposicion",
        categoria_segura=True,
        descripcion_corta=recortar(item["detalle"]),
        lugar=LUGAR,
        funciones=funciones_de_muestra(None, None, ahora),
        entradas=[Entrada(url=url, via=NOMBRE)],
        productor="Museo Torres García",
        muestra=True,
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos = [e for item in actuales(cliente.texto(f"{BASE}/exposiciones.php")) if (e := armar_muestra(item, ahora))]
    return eventos, []
