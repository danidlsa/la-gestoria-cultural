"""Coordenadas para las salas que ninguna fuente ubica, con Nominatim (OpenStreetMap).

Gratis, sin API key y con una política de uso estricta (operations.osmfoundation.org/policies/nominatim):
un pedido por segundo, User-Agent propio y caché de resultados. Cada dirección se consulta una sola
vez; las que no se encuentran se reintentan recién después de un mes.

No usa `cartelera.http.Cliente` porque ese cliente aplica robots.txt, que en Nominatim está pensado
para rastreadores; el uso de la API lo regula su política de uso, que esto respeta.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from cartelera.geo import en_montevideo
from cartelera.http import USER_AGENT

CACHE = Path("datos/cache/geocodificacion.json")
URL = "https://nominatim.openstreetmap.org/search"
MAX_CONSULTAS = 25  # por corrida
REINTENTAR_FALLIDAS = timedelta(days=30)
log = logging.getLogger(__name__)


class Geocodificador:
    def __init__(self):
        self._http: httpx.Client | None = None
        self._ultimo = 0.0
        self._consultas = 0
        try:
            self._cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self._cache = {}

    def __call__(self, consulta: str) -> tuple[float, float] | None:
        """(lat, lon) de una dirección o nombre de sala en Montevideo, o None."""
        clave = consulta.strip().lower()
        guardado = self._cache.get(clave)
        if guardado and (guardado["punto"] or datetime.now() - datetime.fromisoformat(guardado["fecha"]) < REINTENTAR_FALLIDAS):
            return tuple(guardado["punto"]) if guardado["punto"] else None
        if self._consultas >= MAX_CONSULTAS:
            return None
        self._consultas += 1
        punto = None
        try:
            self._http = self._http or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
            time.sleep(max(0.0, self._ultimo + 1.1 - time.monotonic()))  # máximo un pedido por segundo
            self._ultimo = time.monotonic()
            respuesta = self._http.get(URL, params={
                "format": "json", "limit": 1, "countrycodes": "uy", "q": f"{consulta}, Montevideo, Uruguay",
            })
            respuesta.raise_for_status()
            resultados = respuesta.json()
            if resultados:
                lat, lon = float(resultados[0]["lat"]), float(resultados[0]["lon"])
                punto = (lat, lon) if en_montevideo(lat, lon) else None
        except Exception as error:  # noqa: BLE001 - sin geocodificación la sala queda sin ubicar, nada más
            log.warning("geocodificar %r: %s", consulta, error)
            return None
        self._cache[clave] = {"punto": list(punto) if punto else None, "fecha": datetime.now().isoformat()}
        return punto

    def guardar(self) -> None:
        if self._http:
            self._http.close()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(self._cache, ensure_ascii=False, indent=0), encoding="utf-8")
