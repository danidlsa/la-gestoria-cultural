"""Cuánto se camina, por la calle, entre los lugares de un especial (para "Mi recorrido").

Se calcula al generar el sitio, con el ruteo a pie de OpenStreetMap que ofrece FOSSGIS (routing.openstreetmap.de,
el mismo que usa openstreetmap.org). Un solo pedido trae la tabla de distancias y tiempos entre todos los lugares;
se guarda en caché y solo se vuelve a pedir si aparece un lugar nuevo o se mueve uno. Así quien usa la web no
le manda nada a nadie: las distancias ya vienen en la página.

Política de uso de FOSSGIS: User-Agent propio, como mucho un pedido por segundo, nada de uso intensivo, y mostrar
la atribución con un enlace para arreglar el mapa (va en la página, debajo del recorrido).
"""

import json
import logging
from pathlib import Path

import httpx

from cartelera.http import USER_AGENT

CACHE = Path("datos/cache/caminatas.json")
URL = "https://routing.openstreetmap.de/routed-foot/table/v1/foot/{puntos}?annotations=distance,duration"
MAX_LUGARES = 100  # lo que acepta una tabla de OSRM
log = logging.getLogger(__name__)


def _punto(lat: float, lon: float) -> str:
    return f"{lat:.5f},{lon:.5f}"


def _clave(a: str, b: str) -> str:
    return "|".join(sorted((a, b)))


def caminatas(lugares: dict[str, tuple[float, float]], cache: Path = CACHE, pedir=None) -> dict[str, list[int]]:
    """{"id_a|id_b": [metros, minutos]} para cada par de lugares (ids ordenados), caminando por la calle."""
    try:
        guardadas = json.loads(cache.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        guardadas = {}
    ids = sorted(lugares)
    puntos = {i: _punto(*lugares[i]) for i in ids}
    faltan = [(a, b) for n, a in enumerate(ids) for b in ids[n + 1:] if _clave(puntos[a], puntos[b]) not in guardadas]
    if faltan and len(ids) <= MAX_LUGARES:
        try:
            tabla = (pedir or _pedir)([lugares[i] for i in ids])
            for n, a in enumerate(ids):
                for m, b in enumerate(ids[n + 1:], start=n + 1):
                    # A pie, ida y vuelta casi siempre dan lo mismo: se toma el promedio.
                    metros = (tabla["distances"][n][m] + tabla["distances"][m][n]) / 2
                    segundos = (tabla["durations"][n][m] + tabla["durations"][m][n]) / 2
                    guardadas[_clave(puntos[a], puntos[b])] = [round(metros), max(1, round(segundos / 60))]
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(guardadas, indent=0), encoding="utf-8")
        except Exception as error:  # noqa: BLE001 - sin tabla, la página estima en línea recta
            log.warning("caminatas: %s", error)
    resultado = {}
    for n, a in enumerate(ids):
        for b in ids[n + 1:]:
            valor = guardadas.get(_clave(puntos[a], puntos[b]))
            if valor:
                resultado[_clave(a, b)] = valor
    return resultado


def _pedir(coordenadas: list[tuple[float, float]]) -> dict:
    puntos = ";".join(f"{lon:.5f},{lat:.5f}" for lat, lon in coordenadas)
    respuesta = httpx.get(URL.format(puntos=puntos), headers={"User-Agent": USER_AGENT}, timeout=60)
    respuesta.raise_for_status()
    datos = respuesta.json()
    if datos.get("code") != "Ok":
        raise ValueError(f"respuesta {datos.get('code')}")
    return datos


def precalcular(ahora=None) -> None:
    """Deja en la caché las caminatas de los especiales que se muestran (corre al unificar, antes de guardar los
    datos en la rama `datos`: así la caché queda guardada y la tabla no se vuelve a pedir en cada corrida)."""
    from datetime import datetime

    from cartelera import especiales
    from cartelera.scrapers.base import MONTEVIDEO

    if not especiales.activo():
        return
    ahora = ahora or datetime.now(MONTEVIDEO)
    eventos = json.loads(Path("datos/eventos.json").read_text(encoding="utf-8"))["eventos"]
    ciclos = json.loads(Path("datos/ciclos.json").read_text(encoding="utf-8"))["ciclos"]
    lugares = {lugar["id"]: lugar for lugar in json.loads(Path("datos/lugares.json").read_text(encoding="utf-8"))["lugares"]}
    for armado in especiales.armar(eventos, ciclos, ahora.date()):
        ubicados = {
            e["lugar_id"]: (lugares[e["lugar_id"]]["lat"], lugares[e["lugar_id"]]["lon"])
            for e in armado["eventos"] if lugares.get(e["lugar_id"], {}).get("lat") is not None
        }
        if len(ubicados) > 1:
            log.info("caminatas: %s, %s pares", armado["id"], len(caminatas(ubicados)))

