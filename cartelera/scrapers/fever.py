"""Fever: experiencias en Montevideo, sobre todo los conciertos Candlelight.

Las páginas de Fever traen JSON-LD. Las experiencias con fecha (conciertos, obras) tienen un objeto
`Event` con fecha, lugar con coordenadas y precios; los tours y talleres sin fecha solo tienen un
`Product` y no se toman: no tienen funciones y muchos están pensados para turistas.
"""

import re
from datetime import datetime

from cartelera.categorias import clasificar, esta_cancelado
from cartelera.extraer import jsonld_de_tipo, recortar
from cartelera.geo import en_montevideo
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo, Precio

NOMBRE = "fever"
BASE = "https://feverup.com"
# Las secciones donde aparecen las experiencias con fecha.
LISTADOS = ["", "/candlelight", "/eventos-musicales", "/teatro-comedia-espectaculos", "/ballet"]


def ids_de_listado(pagina: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r'href="(?:https://feverup\.com)?/m/(\d+)"', pagina)))


def armar_evento(evento: dict, ahora: datetime) -> EventoCrudo | None:
    titulo = (evento.get("name") or "").strip()
    inicio = evento.get("startDate")
    if not titulo or not inicio or esta_cancelado(titulo) or "Cancelled" in (evento.get("eventStatus") or ""):
        return None
    lugar = evento.get("location") or {}
    geo = lugar.get("geo") or {}
    lat, lon = geo.get("latitude"), geo.get("longitude")
    if lat is None or not en_montevideo(lat, lon):
        return None
    inicio = datetime.fromisoformat(inicio)
    if inicio.date() < ahora.date():
        return None
    fin = datetime.fromisoformat(evento["endDate"]) if evento.get("endDate") else None
    ofertas = evento.get("offers") or []
    ofertas = ofertas if isinstance(ofertas, list) else [ofertas]
    precios = [float(o["price"]) for o in ofertas if o.get("price") is not None and o.get("priceCurrency", "UYU") == "UYU"]
    url = evento.get("url") or ""
    descripcion = evento.get("description") or ""
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=url.rstrip("/").rsplit("/", 1)[-1],
        url=url,
        titulo=titulo,
        categoria=clasificar(titulo, descripcion, por_defecto="musica"),
        descripcion_corta=recortar(descripcion),
        lugar=LugarCrudo(nombre=(lugar.get("name") or "").strip(), lat=lat, lon=lon),
        funciones=[Funcion(inicio=inicio, fin=fin if fin and fin > inicio else None)],
        precio=Precio(desde=min(precios), hasta=max(precios)) if precios else None,
        entradas=[Entrada(url=url, via=NOMBRE)],
        imagen_url=evento.get("image") if isinstance(evento.get("image"), str) else None,
        productor="Fever",
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    ids: list[str] = []
    for listado in LISTADOS:
        ids += ids_de_listado(cliente.texto(f"{BASE}/es/montevideo-uruguay{listado}"))
    eventos, errores = [], []
    for ident in dict.fromkeys(ids):
        try:
            for objeto in jsonld_de_tipo(cliente.texto(f"{BASE}/m/{ident}"), "Event"):
                evento = armar_evento(objeto, ahora)
                if evento:
                    eventos.append(evento)
        except Exception as error:  # noqa: BLE001 - una página rota no frena el resto
            errores.append(f"{ident}: {type(error).__name__}: {error}")
    return eventos, errores
