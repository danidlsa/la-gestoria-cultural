"""Tikzet: ticketera "sin cargo por servicio" que usan salas y productoras independientes (El Hormiguero, Tatu…).

La cartelera de tikzet.com es una app que lee una API pública (api.tikzet.com, sin restricciones en su
robots.txt): `/events/popular` trae todo lo que viene, de toda Latinoamérica, de a 96 por página (unas 7
páginas); de ahí se quedan los de Uruguay (`country` 11) y se pide la ficha de cada uno (`/events/by-slug/…`),
que suma la organización, la descripción, el horario y el precio. La sala es la organización; la ubicación sale
de la dirección (si no cae en Montevideo, el evento queda afuera al unificar).

Además de espectáculos hay cursos, cenas y rifas: esos se dejan afuera por el título.
"""

import re
from datetime import datetime, timezone

from cartelera.categorias import clasificar, es_deporte, esta_cancelado
from cartelera.extraer import recortar, texto_plano
from cartelera.geo import sin_tildes
from cartelera.scrapers.instagram_bares import lugar_del_texto
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo, Precio
from cartelera.scrapers.base import cargar
from cartelera.scrapers.mientrada import HORA_DE_FIESTA

NOMBRE = "tikzet"
API = "https://api.tikzet.com"
WEB = "https://www.tikzet.com/events"
URUGUAY = 11
POR_PAGINA = 96  # el máximo que acepta la API
MAX_PAGINAS = 20
# Lo que no es una salida cultural: clases de cocina, cenas, rifas, capacitaciones.
_AFUERA = re.compile(
    r"\b(rifa|curso|cena|cocina|tapeo|alfajor\w*|pan sin gluten|gesti[oó]n de crisis|capacitaci[oó]n|webinar|"
    r"seminario|congreso|simposio)\b", re.I,
)


def listado(cliente: Cliente, ahora: datetime) -> list[dict]:
    """Todos los eventos que vienen (de todos los países), página por página."""
    desde = ahora.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    eventos = []
    for pagina in range(MAX_PAGINAS):
        datos = cliente.get(f"{API}/events/popular?search=&limit={POR_PAGINA}&offset={pagina * POR_PAGINA}"
                            f"&startDateFrom={desde}").json()
        eventos += datos.get("events") or []
        if not datos.get("isNextPageAvailable"):
            break
    return eventos


def _fecha(texto: str, zona) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(zona)


def armar_evento(ficha: dict, ahora: datetime) -> EventoCrudo | None:
    titulo = texto_plano(ficha.get("name"))
    if not titulo or ficha.get("country") != URUGUAY or ficha.get("finished") or esta_cancelado(titulo) or es_deporte(titulo):
        return None
    if _AFUERA.search(titulo):
        return None
    organizacion = ficha.get("organization") or {}
    sala = texto_plano(organizacion.get("name"))
    # La organización suele ser la sala (El Hormiguero, El Chamuyo); si es una productora, la sala es la dirección.
    productora = sala if re.search(r"producci[oó]n|productora|eventos\b|crew\b", sala, re.I) else None
    if productora:
        sala = ""
    direccion = texto_plano(ficha.get("address")) or None
    # Si la descripción dice dónde es ("📍 Sala Ducón, Montevideo"), eso manda: a veces la organización es una
    # productora con un nombre que no lo dice (Piffa).
    en_el_texto, _ = lugar_del_texto(ficha.get("description") or "")
    if en_el_texto and sin_tildes(en_el_texto).lower() not in ("montevideo", "uruguay"):
        sala = en_el_texto
    if not sala and not direccion:
        return None
    # Las series traen sus fechas en `dates`; un evento suelto, en `startDateTime` y `endDateTime`.
    tramos = [(d.get("startDateTime"), d.get("endDateTime")) for d in ficha.get("dates") or [] if d.get("startDateTime")]
    tramos = tramos or [(ficha.get("startDateTime"), ficha.get("endDateTime"))]
    funciones = []
    for inicio, fin in tramos:
        if not inicio:
            continue
        empieza = _fecha(inicio, ahora.tzinfo)
        termina = _fecha(fin, ahora.tzinfo) if fin else None
        if empieza.date() >= ahora.date():
            funciones.append(Funcion(inicio=empieza, fin=termina if termina and termina > empieza else None))
    if not funciones:
        return None
    descripcion = texto_plano(ficha.get("description"))
    # Casi todo lo que se vende por Tikzet en Montevideo son shows de música en salas chicas.
    categoria = clasificar(titulo, descripcion, por_defecto="musica")
    hora = funciones[0].inicio.time()
    if categoria == "musica" and (hora >= HORA_DE_FIESTA or hora.hour < 6) and re.search(r"\b(club|party|fiesta|dj)\b", titulo, re.I):
        categoria = "fiesta"
    precio_base = (ficha.get("cheapestProduct") or {}).get("price", ficha.get("basePrice"))
    precio = None
    if precio_base is not None:
        precio = Precio(desde=float(precio_base), hasta=float(precio_base), gratis=float(precio_base) == 0)
    url = f"{WEB}/{ficha['slug']}"
    flyer = next((f.get("url") for f in ficha.get("flyers") or [] if f.get("url") and not f.get("isVideo")), None)
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=str(ficha.get("id") or ficha["slug"]),
        url=url,
        titulo=titulo,
        categoria=categoria,
        descripcion_corta=recortar(descripcion),
        lugar=LugarCrudo(nombre=sala or direccion, direccion=direccion),
        funciones=funciones,
        precio=precio,
        entradas=[Entrada(url=url, via=NOMBRE)],
        imagen_url=flyer,
        productor=productora or sala or None,
    )


def agotados(cliente: Cliente, ahora: datetime, vistos: set[str], anteriores: list[EventoCrudo]) -> list[EventoCrudo]:
    """Los de la corrida anterior que ya no están en la cartelera de Tikzet pero siguen en pie: agotados.

    Tikzet saca de su cartelera lo que se agotó (el tributo a Shakira en El Hormiguero, 20/11/2026), pero la ficha
    sigue ahí y sin terminar. Así no desaparecen del sitio: quedan con "agotado".
    """
    resultado = []
    for previo in anteriores:
        slug = previo.url.rstrip("/").rsplit("/", 1)[-1]
        if slug in vistos or not any(f.inicio >= ahora for f in previo.funciones):
            continue
        try:
            ficha = cliente.get(f"{API}/events/by-slug/{slug}").json()
            armado = armar_evento(ficha.get("event", ficha), ahora)
        except Exception:  # noqa: BLE001 - si la ficha ya no existe (la bajaron), no hay nada que mostrar
            continue
        if armado:
            resultado.append(armado.model_copy(update={"funciones": [f.model_copy(update={"agotada": True}) for f in armado.funciones]}))
    return resultado


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores, vistos = [], [], set()
    for item in listado(cliente, ahora):
        if item.get("country") != URUGUAY or _AFUERA.search(item.get("name") or ""):
            continue  # ni se pide la ficha
        vistos.add(item["slug"])
        try:
            ficha = cliente.get(f"{API}/events/by-slug/{item['slug']}").json()
            armado = armar_evento(ficha.get("event", ficha), ahora)
        except Exception as error:  # noqa: BLE001 - una ficha rota no frena las demás
            errores.append(f"{item.get('slug')}: {type(error).__name__}: {error}")
            continue
        if armado:
            eventos.append(armado)
    anterior = cargar(NOMBRE)
    eventos += agotados(cliente, ahora, vistos, anterior.eventos if anterior else [])
    return eventos, errores
