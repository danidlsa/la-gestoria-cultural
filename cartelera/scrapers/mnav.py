"""Museo Nacional de Artes Visuales: exposiciones actuales y próximas, y actividades con fecha y hora.

Sitio en PHP propio con HTML del servidor. Las exposiciones traen el período ("05 de Ago, 2026 - 28 de
Feb, 2027") y las actividades, el día y la hora ("Miércoles 04 de Nov, 2026. 16:30 h").
"""

import html
import re
from datetime import date, datetime, time

from cartelera.categorias import esta_cancelado
from cartelera.extraer import texto_plano
from cartelera.geo import sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo, Precio
from cartelera.scrapers.muestras import funciones_de_muestra, mes_de

NOMBRE = "mnav"
BASE = "https://mnav.gub.uy"
LUGAR = LugarCrudo(
    nombre="Museo Nacional de Artes Visuales", direccion="Tomás Giribaldi 2283, Parque Rodó", lat=-34.91384, lon=-56.16497,
)
LISTADOS_EXPOSICIONES = ["/cms.php?id=expos&t=2", "/cms.php?id=expos&t=3"]  # actuales y próximas
ACTIVIDADES = "/cms.php?id=actividades"
# Cada ítem es un enlace con su título y su fecha adentro. Lo de en medio no puede cerrar el enlace: si no, el primer
# ítem se quedaba con el enlace del menú del sitio ("Juegos") que está antes de la lista.
_ITEM = re.compile(
    r'<a href="/?(cms\.php\?id=[^"]+)"[^>]*>(?:(?!</a>).)*?<p class="w-ccc[^>]*>(.*?)</p>\s*<p class="w-cc[^>]*>(.*?)</p>', re.S,
)
_FECHA = re.compile(r"(\d{1,2}) de ([a-z]+),? (\d{4})")
_HORA = re.compile(r"(\d{1,2})[:.](\d{2})\s*h")
# Rubro de una actividad según su título.
_RUBROS = [
    ("taller", re.compile(r"\b(taller|curso|clase|seminario)\w*")),
    ("tour", re.compile(r"\b(visitas? (guiadas?|mediadas?)|recorrido)")),
    ("cine", re.compile(r"\b(proyeccion|cine|pelicula|documental)")),
    ("musica", re.compile(r"\b(concierto|recital)")),
]


def leer_listado(pagina: str) -> list[tuple[str, str, str]]:
    """(enlace, título, fecha en texto) de cada ítem."""
    return [(html.unescape(e), texto_plano(t), texto_plano(f)) for e, t, f in _ITEM.findall(pagina)]


def fechas(texto: str) -> list[date]:
    encontradas = []
    for dia, mes, anio in _FECHA.findall(sin_tildes(texto)):
        if numero := mes_de(mes):
            encontradas.append(date(int(anio), numero, int(dia)))
    return encontradas


def imagen(enlace: str) -> str:
    return f"{BASE}/img.php?p={enlace.split('=')[1].split('&')[0]}"


def armar_exposicion(enlace: str, titulo: str, periodo: str, ahora: datetime, con_imagen: bool = True) -> EventoCrudo | None:
    rango = fechas(periodo)
    if not titulo or not rango or esta_cancelado(titulo):
        return None
    desde, hasta = rango[0], rango[-1]
    if hasta < ahora.date():
        return None
    funciones = funciones_de_muestra(desde, hasta, ahora)
    if not funciones:
        return None
    return EventoCrudo(
        fuente=NOMBRE,
        # El sitio a veces repite el mismo enlace para dos exposiciones: el id lleva también el título.
        id_externo=f"{enlace.split('=')[1].split('&')[0]}-{sin_tildes(titulo)[:40]}",
        url=f"{BASE}/{enlace}",
        titulo=titulo,
        categoria="exposicion",
        categoria_segura=True,
        lugar=LUGAR,
        funciones=funciones,
        precio=Precio(desde=0, hasta=0, gratis=True),
        entradas=[Entrada(url=f"{BASE}/{enlace}", via=NOMBRE)],
        imagen_url=imagen(enlace) if con_imagen else None,
        productor="Museo Nacional de Artes Visuales",
        muestra=True,
        hasta=hasta,
    )


def armar_actividad(enlace: str, titulo: str, cuando: str, ahora: datetime) -> EventoCrudo | None:
    dias = fechas(cuando)
    if not titulo or not dias or esta_cancelado(titulo):
        return None
    hora = _HORA.search(cuando)
    inicio = datetime.combine(dias[0], time(int(hora.group(1)), int(hora.group(2))) if hora else time(0, 0), tzinfo=ahora.tzinfo)
    if inicio.date() < ahora.date():
        return None
    plano = sin_tildes(titulo)
    rubro = next((r for r, patron in _RUBROS if patron.search(plano)), "charla")
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=enlace.split("=")[1].split("&")[0],
        url=f"{BASE}/{enlace}",
        titulo=titulo,
        categoria=rubro,
        lugar=LUGAR,
        funciones=[Funcion(inicio=inicio, sin_hora=not hora)],
        entradas=[Entrada(url=f"{BASE}/{enlace}", via=NOMBRE)],
        imagen_url=imagen(enlace),
        productor="Museo Nacional de Artes Visuales",
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    exposiciones = [item for listado in LISTADOS_EXPOSICIONES for item in leer_listado(cliente.texto(f"{BASE}{listado}"))]
    # Con un enlace repetido, la imagen sería la de otra exposición: mejor sin imagen.
    repetidos = {e for e in (i[0] for i in exposiciones) if sum(1 for i in exposiciones if i[0] == e) > 1}
    for enlace, titulo, periodo in exposiciones:
        if evento := armar_exposicion(enlace, titulo, periodo, ahora, con_imagen=enlace not in repetidos):
            eventos.append(evento)
    for enlace, titulo, cuando in leer_listado(cliente.texto(f"{BASE}{ACTIVIDADES}")):
        if evento := armar_actividad(enlace, titulo, cuando, ahora):
            eventos.append(evento)
    return eventos, errores
