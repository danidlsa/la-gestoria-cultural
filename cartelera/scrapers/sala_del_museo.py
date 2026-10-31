"""Sala del Museo (del Carnaval): Joomla con el componente ZOO, HTML del servidor.

`/shows.html` lista los shows y cada ficha (`/shows/item/<slug>.html`) trae la fecha ("22 de Noviembre
2026"), la hora ("20hs") y el enlace a RedTickets, así que el cruce con RedTickets es exacto. La sala
suma los shows que todavía no están a la venta y una imagen propia.
"""

import html
import re
from datetime import date, datetime, time

from cartelera.categorias import clasificar, esta_cancelado
from cartelera.extraer import recortar, texto_plano
from cartelera.geo import sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo
from cartelera.scrapers.mvd_cms import MESES

NOMBRE = "sala_del_museo"
BASE = "https://www.saladelmuseo.com.uy"
LUGAR = LugarCrudo(nombre="Sala del Museo", direccion="Rambla 25 de Agosto esq. Maciel", lat=-34.905789, lon=-56.212222)
_FECHA = re.compile(r"(\d{1,2})\s+de\s+([a-z]+)\s+(\d{4})")
_HORA = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*h")


def enlaces_de_listado(pagina: str) -> list[str]:
    return [f"{BASE}{ruta}" for ruta in dict.fromkeys(re.findall(r'href="(/shows/item/[\w-]+\.html)"', pagina))]


def _clase(pagina: str, clase: str) -> str:
    encontrado = re.search(rf'class="element [^"]*\b{clase}"[^>]*>(.*?)</li>(?!\s*<li>)', pagina, re.S)
    return encontrado.group(1) if encontrado else ""


def parsear_ficha(pagina: str, url: str, ahora: datetime) -> EventoCrudo | None:
    titulo = re.search(r'<h1 class="uk-article-title">(.*?)</h1>', pagina, re.S)
    titulo = texto_plano(titulo.group(1)) if titulo else ""
    if not titulo or esta_cancelado(titulo):
        return None
    hora = _HORA.search(sin_tildes(texto_plano(_clase(pagina, "hora"))))
    funciones = []
    for dia, mes, anio in _FECHA.findall(sin_tildes(texto_plano(_clase(pagina, "fecha")))):
        if mes not in MESES:
            continue
        fecha = date(int(anio), MESES[mes], int(dia))
        if fecha < ahora.date():
            continue
        if hora:
            inicio = datetime.combine(fecha, time(int(hora.group(1)) % 24, int(hora.group(2) or 0)), tzinfo=ahora.tzinfo)
            funciones.append(Funcion(inicio=inicio))
        else:
            funciones.append(Funcion(inicio=datetime.combine(fecha, time(0, 0), tzinfo=ahora.tzinfo), sin_hora=True))
    if not funciones:
        return None

    descripcion = re.search(r'<div class="uk-margin pos-content">(.*?)</div>', pagina, re.S)
    descripcion = texto_plano(descripcion.group(1)) if descripcion else ""
    compras = [html.unescape(c) for c in dict.fromkeys(re.findall(r'href="(https://(?:www\.)?redtickets\.uy/evento/[^"]+)"', pagina))]
    medios = pagina[pagina.find("pos-media"):]
    imagen = re.search(r'<img[^>]+src="(/media/[^"]+)"', medios)
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=url.rsplit("/", 1)[-1].removesuffix(".html"),
        url=url,
        titulo=titulo,
        # Es una sala de música: solo el título puede decir otra cosa. La descripción nombra al "Museo del
        # Carnaval" y menciona de todo; si el show está en RedTickets, la categoría sale de ahí.
        categoria=clasificar(titulo, por_defecto="musica"),
        descripcion_corta=recortar(descripcion),
        lugar=LUGAR,
        funciones=funciones,
        entradas=[Entrada(url=c, via="redtickets") for c in compras] or [Entrada(url=url, via=NOMBRE)],
        imagen_url=f"{BASE}{imagen.group(1)}" if imagen else None,
        enlaces=compras,
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for url in enlaces_de_listado(cliente.texto(f"{BASE}/shows.html")):
        try:
            evento = parsear_ficha(cliente.texto(url), url, ahora)
        except Exception as error:  # noqa: BLE001 - una ficha rota no frena el resto
            errores.append(f"{url}: {type(error).__name__}: {error}")
            continue
        if evento:
            eventos.append(evento)
    return eventos, errores
