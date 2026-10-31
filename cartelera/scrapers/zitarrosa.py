"""Sala Zitarrosa: la página de programación lista lo próximo y cada ficha trae funciones, precios y promos.

Casi todo se vende por Tickantel y la ficha enlaza ahí, así que el cruce con Tickantel es exacto. La
Zitarrosa suma la sala interna, las promociones (la diaria, Club El País) y los ciclos (MAREA, Fest Jazz).
El sitio solo responde desde Uruguay, así que esta fuente corre local (no en GitHub Actions).
"""

import html
import re
from datetime import datetime, time

from cartelera.beneficios import beneficios_de_entradas
from cartelera.categorias import clasificar, esta_cancelado
from cartelera.extraer import precio_de, recortar, texto_plano
from cartelera.geo import sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo, Precio
from cartelera.scrapers.cartelera_mvd import fecha_de
from cartelera.scrapers.mvd_cms import GENEROS

NOMBRE = "zitarrosa"
BASE = "https://salazitarrosa.montevideo.gub.uy"
LUGAR = LugarCrudo(nombre="Sala Zitarrosa", direccion="Av. 18 de Julio 1012", lat=-34.90626, lon=-56.19441)
_FUNCION = re.compile(
    r'fa-calendar"></i>\s*<span>([^<]+)</span>.*?fa-clock"></i>\s*<span>\s*(\d{1,2}):(\d{2})\s*([AP]M)?', re.S | re.I,
)
# "Lucía Chappe – Ciclo MAREA", "Coltrane 100 años – 19° Fest Jazz Mvd": el ciclo va al final del título.
_CICLO_EN_TITULO = re.compile(r"^(.+?)\s+[–-]\s+((?:ciclo|\d+°?\s*fest)\b.*)$", re.I)


def enlaces_de_listado(pagina: str) -> list[str]:
    return list(dict.fromkeys(re.findall(rf'href="({re.escape(BASE)}/espectaculo/[^"]+)"', pagina)))


def _hora(hora: str, minuto: str, meridiano: str | None) -> time:
    """'08:00', 'PM' -> 20:00."""
    h = int(hora)
    if meridiano:
        h = h % 12 + (12 if meridiano.upper() == "PM" else 0)
    return time(h, int(minuto))


def _lineas(bloque: str, icono: str) -> list[str]:
    return [texto_plano(l) for l in re.findall(rf'<p><i class="fas {icono}"\s*></i>(.*?)</p>', bloque, re.S)]


def parsear_ficha(pagina: str, url: str, ahora: datetime) -> EventoCrudo | None:
    titulo = re.search(r'<h1 class="title--evento">(.*?)</h1>', pagina, re.S)
    titulo = texto_plano(titulo.group(1)) if titulo else ""
    if not titulo or esta_cancelado(titulo):
        return None
    ciclo = None
    if encontrado := _CICLO_EN_TITULO.match(titulo):
        titulo, ciclo = encontrado.group(1).strip(), encontrado.group(2).strip()

    datos = pagina[pagina.find("singleEvent_data"):pagina.find('class="compartir"')]
    hoy = ahora.date()
    funciones = []
    for dia, hora, minuto, meridiano in _FUNCION.findall(datos):
        fecha = fecha_de(html.unescape(dia), hoy)
        if fecha:
            funciones.append(Funcion(inicio=datetime.combine(fecha, _hora(hora, minuto, meridiano), tzinfo=ahora.tzinfo)))
    if not funciones:
        return None

    salas = re.findall(r'href="[^"]*/sala/[^"]*">\s*([^<]+)<', pagina)
    for funcion in funciones:
        funcion.sala = html.unescape(salas[0]).strip() if salas else None
    genero = re.search(r'href="[^"]*/programacion/([\w-]+)"', pagina)
    descripcion = re.search(r'<div class="mb-5">(.*?)</div>', pagina, re.S)
    descripcion = texto_plano(descripcion.group(1)) if descripcion else ""
    categoria = GENEROS.get(sin_tildes(genero.group(1)).replace("-", " ")) if genero else None

    # Las anticipadas son precios por tiempo limitado: no cuentan para el rango de precios.
    tickets = [l for l in _lineas(datos, "fa-ticket-alt") if not re.search(r"anticipad", l, re.I)]
    if any(re.search(r"entrada libre|gratis", l, re.I) for l in tickets) or re.search(r"Entrada libre", datos):
        precio = Precio(desde=0, hasta=0, gratis=True)
    else:
        precio = precio_de("; ".join(tickets)) if tickets else None
    # Algunas fichas enlazan a la portada de Tickantel ("/ng"): esas no sirven para cruzar.
    compras = [html.unescape(c) for c in dict.fromkeys(re.findall(r'href="(https://tickantel[^"]+)"', datos))]
    especificas = [c for c in compras if re.search(r"/\d{6,}", c)]
    imagen = re.search(r'<img class="singleEvent_thumb" src="([^"]+)"', pagina)

    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=url.rstrip("/").rsplit("/", 1)[-1],
        url=url,
        titulo=titulo,
        categoria=categoria or clasificar(titulo, descripcion, por_defecto="musica"),
        categoria_segura=bool(categoria),
        descripcion_corta=recortar(descripcion),
        lugar=LUGAR,
        funciones=funciones,
        precio=precio,
        entradas=[Entrada(url=c, via="tickantel") for c in especificas] or [Entrada(url=url, via=NOMBRE)],
        beneficios=beneficios_de_entradas(_lineas(datos, "fa-gift"), url),
        imagen_url=imagen.group(1) if imagen else None,
        enlaces=especificas,
        ciclo=ciclo,
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for url in enlaces_de_listado(cliente.texto(f"{BASE}/programacion/")):
        try:
            evento = parsear_ficha(cliente.texto(url), url, ahora)
        except Exception as error:  # noqa: BLE001 - una ficha rota no frena el resto
            errores.append(f"{url}: {type(error).__name__}: {error}")
            continue
        if evento:
            eventos.append(evento)
    return eventos, errores
