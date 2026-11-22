"""Peatonal Tours: los recorridos a pie de su web (peatonaltours.uy), con sus fechas y su punto de encuentro.

Venden casi todo por su propio sistema de reservas; a RedTickets llega uno de vez en cuando. La portada (Next.js)
trae en sus datos internos la lista completa de tours, cada uno con sus fechas ("bookingDates", en UTC), el punto de
encuentro con coordenadas, el precio y la duración. Lo que se publica es lo que tiene una fecha por venir.

Las reservas de cada fecha traen el usuario de quien reservó: eso no se guarda ni se usa.
"""

import json
import re
from datetime import datetime, timedelta

from cartelera.extraer import recortar
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo, Precio

NOMBRE = "peatonal_tours"
BASE = "https://www.peatonaltours.uy"
_TROZO = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)


def tours_de(pagina: str) -> list[dict]:
    """La lista de tours de los datos internos de la portada (los trozos que manda Next.js, unidos)."""
    datos = "".join(json.loads(f'"{trozo}"') for trozo in _TROZO.findall(pagina))
    inicio = datos.find('{"tours":')
    if inicio == -1:
        raise ValueError("la portada ya no trae la lista de tours")
    return json.JSONDecoder().raw_decode(datos, inicio)[0]["tours"]


def evento_de(tour: dict, ahora: datetime) -> EventoCrudo | None:
    duracion = timedelta(minutes=tour.get("duration") or 90)
    funciones = []
    for fecha in tour.get("bookingDates") or []:
        if not fecha.get("active"):
            continue
        inicio = datetime.fromisoformat(fecha["date"].replace("Z", "+00:00")).astimezone(ahora.tzinfo)
        if inicio < ahora:
            continue
        funciones.append(Funcion(inicio=inicio, fin=inicio + duracion, agotada=not fecha.get("canBook", True)))
    if not tour.get("active") or not funciones:
        return None
    lugar = tour.get("location") or {}
    try:
        lat, lon = float(lugar["latitude"]), float(lugar["longitude"])
    except (KeyError, TypeError, ValueError):
        lat = lon = None
    precio = tour.get("price")
    url = f"{BASE}/tour/{tour['id']}"
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=str(tour["id"]),
        url=url,
        titulo=tour["title"].strip(),
        categoria="tour",
        categoria_segura=True,
        descripcion_corta=recortar(tour.get("description")),
        # El lugar es el punto de encuentro ("Fuente de la Plaza Matriz"), como en los otros recorridos.
        lugar=LugarCrudo(nombre=(lugar.get("name") or "Punto de encuentro a confirmar").strip(), lat=lat, lon=lon),
        funciones=sorted(funciones, key=lambda f: f.inicio),
        precio=None if precio is None else Precio(desde=precio, hasta=precio, gratis=precio == 0),
        entradas=[Entrada(url=url, via=NOMBRE)],
        imagen_url=tour.get("imageSrc"),
        productor="Peatonal Tours",
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos = [e for t in tours_de(cliente.texto(f"{BASE}/")) if (e := evento_de(t, ahora))]
    return eventos, []
