"""Entraste: ticketera de fiestas y boliches (Montevideo, la Costa y, en verano, Punta del Este).

La portada es una app de Next.js que trae, en los datos de la página, cada evento: nombre, productora, fecha de
inicio y fin (en UTC), sala con ciudad, precios e imagen. La página de cada evento suma la dirección de la sala con
sus coordenadas y la descripción: se pide solo para los de Montevideo (unos pocos).

Solo entra lo que es en Montevideo, según la ciudad que pone la productora (y, si hay coordenadas, que caigan en
Montevideo). Lo que no dice ni la sala ni la dirección no se puede ubicar en el mapa y queda afuera.
"""

import json
import re
from datetime import datetime

from cartelera.categorias import clasificar, es_deporte, esta_cancelado
from cartelera.extraer import payload_next, recortar, texto_plano
from cartelera.geo import en_montevideo, sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo, Precio
from cartelera.scrapers.mientrada import HORA_DE_FIESTA

NOMBRE = "entraste"
BASE = "https://app.entraste.com"
_OBJETO = re.compile(r'\{"id":\d+,"name":')


def eventos_de_pagina(pagina: str) -> list[dict]:
    """Los eventos que vienen en los datos de la página (sin repetir: un evento puede estar en varias secciones)."""
    texto = payload_next(pagina)
    decodificador = json.JSONDecoder()
    eventos = {}
    for encontrado in _OBJETO.finditer(texto):
        try:
            objeto, _ = decodificador.raw_decode(texto[encontrado.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(objeto, dict) and objeto.get("name_seo") and objeto.get("start_date"):
            eventos.setdefault(objeto["id"], objeto)
    return list(eventos.values())


def es_de_montevideo(evento: dict) -> bool:
    ciudad = sin_tildes((evento.get("venue") or {}).get("city") or "").strip()
    return ciudad == "montevideo"


def armar_evento(evento: dict, ahora: datetime) -> EventoCrudo | None:
    titulo = texto_plano(evento.get("name"))
    sala = (evento.get("venue") or {})
    direccion = texto_plano(sala.get("address")) or None
    # Sin nombre de sala, la dirección hace de nombre ("Plaza Mateo, Rbla. Pdte. Wilson esq, …").
    nombre_sala = texto_plano(sala.get("name")) or (direccion or "").split(",")[0].strip()
    lat, lon = sala.get("latitude"), sala.get("longitude")
    if not titulo or esta_cancelado(titulo) or es_deporte(titulo) or not es_de_montevideo(evento) or not nombre_sala:
        return None
    if lat is not None and not en_montevideo(lat, lon):
        return None
    inicio = datetime.fromisoformat(evento["start_date"].replace("Z", "+00:00")).astimezone(ahora.tzinfo)
    if inicio.date() < ahora.date():
        return None
    fin = datetime.fromisoformat(evento["end_date"].replace("Z", "+00:00")).astimezone(ahora.tzinfo) if evento.get("end_date") else None
    descripcion = texto_plano(evento.get("short_description") or evento.get("description"))
    # Casi todo son fiestas: si el texto no dice otra cosa, lo que arranca de noche tarde es una fiesta.
    # ("Reggaeton & cumbia" a las 23:30 es una fiesta, no un recital.)
    categoria = clasificar(titulo, descripcion, por_defecto="")
    de_noche = inicio.time() >= HORA_DE_FIESTA or inicio.hour < 6
    if categoria in ("", "musica"):
        categoria = "fiesta" if de_noche else "musica"
    precios = [t["price"] for t in evento.get("ticket_types") or [] if t.get("price") and t.get("status") == "ACTIVE"]
    desde = evento.get("min_price") if evento.get("min_price") is not None else (min(precios) if precios else None)
    hasta = evento.get("max_price") if evento.get("max_price") is not None else (max(precios) if precios else None)
    precio = None
    if desde is not None:
        precio = Precio(desde=float(desde), hasta=float(hasta or desde), moneda=evento.get("currency") or "UYU", gratis=float(desde) == 0 and not hasta)
    url = f"{BASE}/events/{evento['name_seo']}"
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=str(evento["id"]),
        url=url,
        titulo=titulo,
        categoria=categoria,
        descripcion_corta=recortar(descripcion),
        lugar=LugarCrudo(nombre=nombre_sala, direccion=direccion, lat=lat, lon=lon),
        funciones=[Funcion(inicio=inicio, fin=fin if fin and fin > inicio else None)],
        precio=precio,
        entradas=[Entrada(url=url, via=NOMBRE)],
        imagen_url=evento.get("image") or None,
        productor=texto_plano(evento.get("producer_name")) or None,
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for evento in eventos_de_pagina(cliente.texto(f"{BASE}/")):
        if not es_de_montevideo(evento) or evento["start_date"][:10] < ahora.date().isoformat():
            continue  # no hace falta pedir su página
        try:
            # La página del evento trae la sala completa (dirección y coordenadas) y la descripción.
            detalle = next((d for d in eventos_de_pagina(cliente.texto(f"{BASE}/events/{evento['name_seo']}"))
                            if d.get("id") == evento["id"]), {})
            armado = armar_evento({**evento, **detalle}, ahora)
        except Exception as error:  # noqa: BLE001 - un evento raro no frena los demás
            errores.append(f"{evento.get('name')}: {type(error).__name__}: {error}")
            continue
        if armado:
            eventos.append(armado)
    return eventos, errores
