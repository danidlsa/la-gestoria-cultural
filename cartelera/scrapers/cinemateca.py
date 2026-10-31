"""Cinemateca: el calendario semanal lista las películas de cada día y los IDs de sus funciones.

El horario de cada función sale de una llamada JSON-RPC (el sitio está hecho con Odoo) y la
duración, de la página de cada película.
"""

import html
import logging
import re
from datetime import date, datetime, time, timedelta

from cartelera.extraer import recortar, texto_plano
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo

NOMBRE = "cinemateca"
BASE = "https://cinemateca.org.uy"
LUGAR = LugarCrudo(nombre="Cinemateca", direccion="Bartolomé Mitre 1236", lat=-34.908515, lon=-56.2008552)
_DIA = re.compile(r'<h4[^>]*>\s*(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo)\s+(\d{1,2})\s*</h4>', re.I)
_BLOQUE = re.compile(r'<div class="col-md-6 mb-3 d-flex">(.*?)(?=<div class="col-md-6 mb-3 d-flex">|<h4|</section>|\Z)', re.S)
log = logging.getLogger(__name__)


def fechas_de_los_dias(numeros: list[int], hoy: date) -> list[date]:
    """'viernes 30', 'sábado 31', 'domingo 1'… -> fechas reales, avanzando desde hoy."""
    fechas, actual = [], hoy - timedelta(days=1)
    for numero in numeros:
        while actual.day != numero:
            actual += timedelta(days=1)
        fechas.append(actual)
        actual += timedelta(days=1)
    return fechas


def leer_calendario(pagina: str, hoy: date) -> dict[str, dict]:
    """{id de película: {titulo, director, imagen, ciclo, funciones: [(fecha, id de función)]}}."""
    cortes = list(_DIA.finditer(pagina))
    fechas = fechas_de_los_dias([int(c.group(1)) for c in cortes], hoy)
    peliculas: dict[str, dict] = {}
    for indice, (corte, fecha) in enumerate(zip(cortes, fechas)):
        fin = cortes[indice + 1].start() if indice + 1 < len(cortes) else len(pagina)
        for bloque in _BLOQUE.findall(pagina[corte.end():fin]):
            pelicula = re.search(r'<a class="text-black fw-bolder" href="/peliculas/(\d+)">([^<]+)</a>', bloque)
            if not pelicula:
                continue
            id_pelicula = pelicula.group(1)
            ficha = peliculas.setdefault(id_pelicula, {
                "titulo": html.unescape(pelicula.group(2)).strip(),
                "director": (re.search(r'<p class="mb-1">de ([^<]+)</p>', bloque) or [None, None])[1],
                "imagen": (re.search(r'<img[^>]+src="([^"]+)"', bloque) or [None, None])[1],
                "ciclo": (re.search(r'href="/ciclos/\d+">([^<]+)</a>', bloque) or [None, None])[1],
                "funciones": [],
            })
            for id_funcion, id_film in re.findall(r'data-event-id="(\d+)" data-film-id="(\d+)"', bloque):
                ficha["funciones"].append((fecha, id_funcion, id_film))
    return peliculas


def duracion_y_sinopsis(pagina: str) -> tuple[int | None, str | None]:
    texto = texto_plano(pagina)
    duracion = re.search(r"Duración:\s*(\d+)\s*min", texto)
    sinopsis = re.search(r"Sinopsis\s+(.+?)(?:Ficha técnica|Síganos|$)", texto)
    return (int(duracion.group(1)) if duracion else None), (sinopsis.group(1).strip() if sinopsis else None)


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    peliculas = leer_calendario(cliente.texto(f"{BASE}/calendario"), ahora.date())
    log.info("cinemateca: %s películas en el calendario semanal", len(peliculas))
    eventos, errores = [], []
    for id_pelicula, ficha in peliculas.items():
        url = f"{BASE}/peliculas/{id_pelicula}"
        try:
            duracion, sinopsis = duracion_y_sinopsis(cliente.texto(url))
            funciones = []
            for fecha, id_funcion, id_film in ficha["funciones"]:
                respuesta = cliente.post_json(
                    f"{BASE}/kc_cinema/widget/event_badge/{id_film}/{id_funcion}",
                    {"jsonrpc": "2.0", "method": "call", "params": {}},
                )
                hora = re.match(r"(\d{1,2}):(\d{2})", (respuesta.get("result") or {}).get("name", ""))
                if not hora:
                    continue
                inicio = datetime.combine(fecha, time(int(hora.group(1)), int(hora.group(2))), tzinfo=ahora.tzinfo)
                if inicio < ahora - timedelta(hours=3):
                    continue
                funciones.append(Funcion(inicio=inicio, fin=inicio + timedelta(minutes=duracion) if duracion else None))
        except Exception as error:  # noqa: BLE001 - una película rota no frena el resto
            errores.append(f"{url}: {type(error).__name__}: {error}")
            continue
        if not funciones:
            continue
        director = f"De {ficha['director'].strip()}. " if ficha["director"] else ""
        eventos.append(EventoCrudo(
            fuente=NOMBRE,
            id_externo=id_pelicula,
            url=url,
            titulo=ficha["titulo"],
            categoria="cine",
            categoria_segura=True,
            descripcion_corta=recortar(director + (sinopsis or "")),
            lugar=LUGAR,
            funciones=sorted(funciones, key=lambda f: f.inicio),
            entradas=[Entrada(url=url, via=NOMBRE)],
            imagen_url=ficha["imagen"],
            productor="Cinemateca Uruguaya",
            ciclo=html.unescape(ficha["ciclo"]).strip() if ficha["ciclo"] else None,
        ))
    return eventos, errores
