"""Beneficios de la diaria: espectáculos con descuento para suscriptores (casi siempre 2x1).

El sitio es un WordPress con la API cerrada, pero el feed RSS de la categoría Espectáculos trae cada
beneficio con "Fecha y hora", "Lugar" y "Precio" en texto, más el enlace a la ticketera. Casi todos
enlazan a RedTickets o Tickantel, así que se unen exacto con el evento que ya está y le suman el
beneficio. Los que no están en ninguna ticketera entran como evento propio, si la fecha se entiende.
"""

import html
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from cartelera.categorias import clasificar, esta_cancelado
from cartelera.extraer import precio_de, recortar, texto_plano
from cartelera.geo import menciona_otra_ciudad, sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Beneficio, Entrada, EventoCrudo, LugarCrudo
from cartelera.scrapers.mvd_cms import GENEROS, funciones_de_texto

NOMBRE = "ladiaria"
FEED = "https://beneficios.ladiaria.com.uy/category/espectaculos/feed/"
MAX_PAGINAS = 10
# Los beneficios más viejos que esto ya no se leen (las fechas sin año serían ambiguas).
ANTIGUEDAD_MAXIMA = timedelta(days=150)
_CAMPO = re.compile(r"(Fecha y hora|Lugar|Precio)\s*:\s*(.*?)(?=(?:Fecha y hora|Lugar|Precio|Sobre el espect\w+)\s*:|$)", re.S)


def items_del_feed(xml: str) -> list[dict]:
    items = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        contenido = re.search(r"<content:encoded><!\[CDATA\[(.*?)\]\]>", item, re.S)
        items.append({
            "titulo": html.unescape(re.search(r"<title>(.*?)</title>", item, re.S).group(1)).strip(),
            "url": re.search(r"<link>(.*?)</link>", item, re.S).group(1).strip(),
            "id": re.search(r"\?p=(\d+)", item).group(1),
            "categorias": re.findall(r"<category><!\[CDATA\[(.*?)\]\]>", item),
            "publicado": parsedate_to_datetime(re.search(r"<pubDate>(.*?)</pubDate>", item).group(1)),
            "html": contenido.group(1) if contenido else "",
        })
    return items


def _campos(texto: str) -> dict[str, str]:
    return {nombre: valor.strip(" .") for nombre, valor in _CAMPO.findall(texto)}


def armar_evento(item: dict, ahora: datetime) -> EventoCrudo | None:
    titulo = item["titulo"]
    texto = texto_plano(item["html"])
    campos = _campos(texto)
    lugar = campos.get("Lugar", "")
    if not lugar or esta_cancelado(titulo) or menciona_otra_ciudad(titulo) or menciona_otra_ciudad(lugar):
        return None
    if ahora - item["publicado"] > ANTIGUEDAD_MAXIMA:
        return None
    # "20.30" o "21.00 horas": se normaliza a "20:30 h" para el lector de fechas compartido.
    fechas = re.sub(r"(\d{1,2})[:.](\d{2})(?:\s*(?:hs?|horas)\b)?", r"\1:\2 h", campos.get("Fecha y hora", ""))
    enlaces = [html.unescape(e) for e in dict.fromkeys(
        re.findall(r'href="(https://(?:www\.)?(?:redtickets\.uy|tickantel\.com\.uy)/[^"]+)"', item["html"])
    )]
    categoria = next((GENEROS[c] for c in map(sin_tildes, item["categorias"]) if c in GENEROS), None)
    sobre = texto.split("Sobre el espectáculo", 1)[-1].split("¿Cómo acceder", 1)[0].lstrip(" :")
    tipo = "2x1" if re.search(r"2\s*[x×]\s*1", texto) else "Descuento"
    # Las fechas no tienen año: se leen desde el día en que se publicó el beneficio, y quedan las que no pasaron.
    publicado = item["publicado"].astimezone(ahora.tzinfo).date()
    funciones = [
        f for f in funciones_de_texto(fechas, publicado, ahora.tzinfo)
        if (f.inicio.date() >= ahora.date() if f.sin_hora else f.inicio >= ahora - timedelta(hours=6))
    ]
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=item["id"],
        url=item["url"],
        titulo=titulo,
        categoria=categoria or clasificar(titulo, sobre, por_defecto="teatro"),
        categoria_segura=categoria is not None,
        descripcion_corta=recortar(sobre),
        lugar=LugarCrudo(nombre=lugar),
        funciones=funciones,
        precio=precio_de(campos.get("Precio", "")),
        entradas=[Entrada(url=e, via="redtickets" if "redtickets" in e else "tickantel") for e in enlaces],
        beneficios=[Beneficio(programa="la diaria", tipo=tipo, url=item["url"])],
        enlaces=enlaces,
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for pagina in range(1, MAX_PAGINAS + 1):
        try:
            items = items_del_feed(cliente.texto(FEED if pagina == 1 else f"{FEED}?paged={pagina}"))
        except Exception:  # noqa: BLE001 - una página que no existe termina la lista
            if pagina == 1:
                raise
            break
        if not items:
            break
        for item in items:
            try:
                evento = armar_evento(item, ahora)
            except Exception as error:  # noqa: BLE001 - un beneficio roto no frena el resto
                errores.append(f"{item.get('url')}: {type(error).__name__}: {error}")
                continue
            if evento:
                eventos.append(evento)
    return eventos, errores
