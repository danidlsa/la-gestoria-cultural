"""Tickantel: el sitemap lista los espectáculos y cada página trae un Event JSON-LD por función.

Las páginas de "alta demanda" (con fila virtual, como La Trampa) no traen el JSON-LD. Para esas, las
funciones se arman con el resumen de la página ("del 12/05/2027 al 15/05/2027 en Antel Arena") y el
horario ("Miércoles, Jueves y Sábado a las 21:00h").
"""

import html
import json
import logging
import re
from datetime import date, datetime, time, timedelta

from cartelera.categorias import categoria_por_lugar, clasificar, es_deporte, esta_cancelado
from cartelera.extraer import jsonld_de_tipo, meta, objeto_json_que_contiene, payload_next, precio_de, recortar, texto_plano
from cartelera.geo import sin_tildes
from cartelera.geo import en_montevideo
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo, Precio

NOMBRE = "tickantel"
SITEMAP = "https://tickantel.com.uy/shows-sitemap.xml"
TIPOS_EVENTO = ("Event", "MusicEvent", "TheaterEvent", "DanceEvent", "ComedyEvent", "Festival", "SportsEvent")
# Funciones que empezaron hace menos de esto todavía se muestran (por ejemplo, el mismo día).
MARGEN_PASADO = timedelta(hours=6)
_RANGO = re.compile(r"(?:del|el) (\d{2})/(\d{2})/(\d{4})(?: al (\d{2})/(\d{2})/(\d{4}))? en (.+?)\.")
_DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
log = logging.getLogger(__name__)


def urls_de_espectaculos(sitemap: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sitemap)))


def id_de_url(url: str) -> str | None:
    encontrado = re.search(r"/espectaculo/(?:[a-z-]+/)?(\d+)", url)
    return encontrado.group(1) if encontrado else None


def _oferta(evento: dict) -> dict:
    oferta = evento.get("offers") or {}
    if isinstance(oferta, list):
        oferta = oferta[0] if oferta else {}
    return oferta


def funciones_canceladas(pagina: str) -> set[str]:
    """Fechas ("AAAA-MM-DDTHH:MM:SS") de funciones canceladas según el payload de la página.

    El JSON-LD a veces sigue diciendo "EventScheduled" aunque la función tenga el aviso
    "Espectáculo cancelado".
    """
    payload = payload_next(pagina)
    inicio = payload.find('"initialFunctions":')
    if inicio < 0:
        return set()
    try:
        funciones, _ = json.JSONDecoder().raw_decode(payload, inicio + len('"initialFunctions":'))
    except json.JSONDecodeError:
        return set()
    return {
        f["date"][:19] for f in funciones
        if isinstance(f, dict) and f.get("date")
        and (f.get("cancelled") is True or esta_cancelado(f.get("announcement")))
    }


def parsear_alta_demanda(pagina: str, url: str, ahora: datetime) -> EventoCrudo | None:
    """Página con fila virtual: sin JSON-LD, las funciones salen del resumen y del horario."""
    resumen = meta(pagina, "og:description") or ""
    rango = _RANGO.search(resumen)
    id_externo = id_de_url(url)
    if not rango or not id_externo:
        return None
    desde = date(int(rango.group(3)), int(rango.group(2)), int(rango.group(1)))
    hasta = date(int(rango.group(6)), int(rango.group(5)), int(rango.group(4))) if rango.group(4) else desde
    datos = objeto_json_que_contiene(payload_next(pagina), "dateRangeLabel") or {}
    horario = sin_tildes(datos.get("schedule") or "")
    hora = re.search(r"(\d{1,2})[:.](\d{2})", horario)
    # "Miércoles, Jueves y Sábado": solo esos días del rango. Sin días nombrados, todos los del rango.
    dias_semana = {n for nombre, n in _DIAS.items() if re.search(rf"\b{nombre}\b", horario)}
    funciones = []
    dia = desde
    while dia <= hasta and len(funciones) < 60:
        if not dias_semana or dia.weekday() in dias_semana:
            inicio = datetime.combine(dia, time(int(hora.group(1)), int(hora.group(2))) if hora else time(0, 0), tzinfo=ahora.tzinfo)
            if inicio >= ahora - MARGEN_PASADO:
                funciones.append(Funcion(inicio=inicio, sin_hora=not hora))
        dia += timedelta(days=1)
    if not funciones:
        return None
    titulo = html.unescape(meta(pagina, "og:title") or "").strip()
    descripcion = texto_plano(datos.get("aboutShow"))
    lugar = rango.group(7).strip()
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=id_externo,
        url=url,
        titulo=titulo,
        # Las de alta demanda casi siempre son recitales grandes.
        categoria=clasificar(titulo, descripcion, por_defecto=categoria_por_lugar(lugar).replace("otros", "musica")),
        descripcion_corta=recortar(descripcion),
        lugar=LugarCrudo(nombre=lugar),
        funciones=funciones,
        precio=precio_de(resumen),
        entradas=[Entrada(url=url, via=NOMBRE)],
        imagen_url=meta(pagina, "og:image"),
    )


def parsear_espectaculo(pagina: str, url: str, ahora: datetime) -> EventoCrudo | None:
    """Arma el evento con las funciones futuras. Devuelve None si no le queda ninguna."""
    eventos = jsonld_de_tipo(pagina, *TIPOS_EVENTO)
    id_externo = id_de_url(url)
    if not id_externo:
        return None
    if not eventos:
        return parsear_alta_demanda(pagina, url, ahora)

    canceladas = funciones_canceladas(pagina)
    funciones, precios = [], []
    for evento in eventos:
        if evento["startDate"][:19] in canceladas:
            continue
        inicio = datetime.fromisoformat(evento["startDate"])
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=ahora.tzinfo)
        if inicio < ahora - MARGEN_PASADO or "Cancelled" in str(evento.get("eventStatus", "")):
            continue
        oferta = _oferta(evento)
        funciones.append(Funcion(inicio=inicio, agotada="SoldOut" in str(oferta.get("availability", ""))))
        if oferta.get("price") not in (None, ""):
            precios.append(float(oferta["price"]))
    if not funciones:
        return None

    primero = eventos[0]
    lugar = primero.get("location") or {}
    geo = lugar.get("geo") or {}
    titulo = html.unescape(primero.get("name", "")).strip()
    descripcion = primero.get("description")
    imagen = primero.get("image")
    if isinstance(imagen, list):
        imagen = imagen[0] if imagen else None
    direccion = (lugar.get("address") or {}).get("streetAddress")

    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=id_externo,
        url=url,
        titulo=titulo,
        # Tickantel no informa la categoría en la página: se infiere por palabras clave.
        categoria=clasificar(titulo, descripcion, por_defecto=categoria_por_lugar(lugar.get("name"))),
        descripcion_corta=recortar(descripcion),
        lugar=LugarCrudo(
            nombre=html.unescape(lugar.get("name", "")).strip() or "Sin lugar",
            direccion=direccion,
            lat=geo.get("latitude"),
            lon=geo.get("longitude"),
        ),
        funciones=sorted(funciones, key=lambda f: f.inicio),
        precio=Precio(desde=min(precios), hasta=max(precios), gratis=max(precios) == 0) if precios else None,
        entradas=[Entrada(url=url, via=NOMBRE)],
        imagen_url=imagen,
    )


def incluir(evento: EventoCrudo) -> bool:
    return (
        en_montevideo(evento.lugar.lat, evento.lugar.lon)
        and not es_deporte(evento.titulo)
        and not esta_cancelado(evento.titulo)
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    urls = urls_de_espectaculos(cliente.texto(SITEMAP))
    log.info("tickantel: %s espectáculos en el sitemap", len(urls))
    eventos, errores = [], []
    for url in urls:
        try:
            evento = parsear_espectaculo(cliente.texto(url), url, ahora)
        except Exception as error:  # noqa: BLE001 - una página rota no frena el resto
            errores.append(f"{url}: {type(error).__name__}: {error}")
            continue
        if evento and incluir(evento):
            eventos.append(evento)
    return eventos, errores
