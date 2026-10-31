"""Gaucho (productora): su web carga los shows de un JSON público, `/data/gaucho-shows.json`.

Cada show trae artista, fecha y hora, sala con dirección y el enlace a las entradas (Tickantel,
RedTickets, Ticketmaster o el sitio del Antel Arena). Sirve para tener los anuncios temprano: el
mismo show después aparece en la ticketera, y se une por el enlace o por sala, día y título.
"""

import re
from datetime import datetime

from cartelera.categorias import esta_cancelado
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo, Precio

NOMBRE = "gaucho"
BASE = "https://www.gaucho.com.uy"
_VIAS = [("tickantel", "tickantel"), ("redtickets", "redtickets"), ("ticketmaster", "ticketmaster_uy"), ("antelarena", "antel_arena")]


def _via(url: str) -> str:
    return next((via for marca, via in _VIAS if marca in url), NOMBRE)


def armar_evento(show: dict, ahora: datetime) -> EventoCrudo | None:
    titulo = (show.get("artist") or "").strip()
    if not titulo or show.get("hidden") or esta_cancelado(titulo):
        return None
    if (show.get("city") or "").strip().lower() != "montevideo":
        return None
    hora = re.match(r"(\d{1,2}):(\d{2})", show.get("hour") or "")
    inicio = datetime(
        int(show["year"]), int(show["month"]), int(show["day"]),
        int(hora.group(1)) if hora else 0, int(hora.group(2)) if hora else 0, tzinfo=ahora.tzinfo,
    )
    if inicio.date() < ahora.date():
        return None
    entradas = (show.get("ticketsLink") or "").strip()
    banner = (show.get("banner") or "").strip()
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=banner or f"{inicio:%Y-%m-%d}-{titulo}",
        url=f"{BASE}/shows.php",
        titulo=titulo,
        categoria="musica",
        descripcion_corta=(show.get("desription") or show.get("description") or "").strip() or None,
        lugar=LugarCrudo(nombre=show.get("venue") or "A confirmar", direccion=show.get("venueAddress") or None),
        funciones=[Funcion(inicio=inicio, sin_hora=not hora, agotada=bool(show.get("soldout")))],
        precio=Precio(desde=0, hasta=0, gratis=True) if show.get("free") else None,
        entradas=[Entrada(url=entradas, via=_via(entradas))] if entradas.startswith("http") else [],
        imagen_url=f"{BASE}/images/banners/{show['year']}/{banner}.jpg" if banner else None,
        productor="Gaucho",
        enlaces=[entradas] if entradas.startswith("http") else [],
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for show in cliente.get(f"{BASE}/data/gaucho-shows.json").json():
        try:
            evento = armar_evento(show, ahora)
        except Exception as error:  # noqa: BLE001 - un show roto no frena el resto
            errores.append(f"{show.get('artist')}: {type(error).__name__}: {error}")
            continue
        if evento:
            eventos.append(evento)
    return eventos, errores
