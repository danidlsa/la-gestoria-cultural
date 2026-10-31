"""Ticketmaster.uy (plataforma Crowder): los conciertos internacionales grandes.

La portada enlaza a cada evento (`/event/<slug>`). La ficha trae, en el JSON con el que arranca la
página (`bootstrapData`), el nombre, la categoría, el lugar con coordenadas y las funciones. Cuando las
funciones no están publicadas (por ejemplo, con las entradas agotadas), la fecha sale de la descripción
("23 de Febrero 2027"). Ticketmaster.uy rechaza las IPs de fuera de Uruguay, así que corre local (no en GitHub Actions).
"""

import json
import re
from datetime import date, datetime, time

from cartelera.categorias import clasificar, esta_cancelado
from cartelera.extraer import recortar, texto_plano
from cartelera.geo import en_montevideo, sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo
from cartelera.scrapers.mvd_cms import GENEROS, MESES

NOMBRE = "ticketmaster_uy"
BASE = "https://www.ticketmaster.uy"
_FECHA = re.compile(r"(\d{1,2})\s+de\s+([a-z]+)\s+(?:de\s+)?(\d{4})")


def slugs_de_portada(pagina: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"(?:\.\./|/)event/([\w-]+)", pagina)))


def datos_de_ficha(pagina: str) -> dict | None:
    inicio = pagina.find("bootstrapData(")
    if inicio < 0:
        return None
    modelo, _ = json.JSONDecoder().raw_decode(pagina[inicio + len("bootstrapData("):])
    return modelo.get("model", {}).get("data")


def _fecha_de_texto(texto: str | None) -> date | None:
    encontrado = _FECHA.search(sin_tildes(texto or ""))
    if not encontrado or encontrado.group(2) not in MESES:
        return None
    return date(int(encontrado.group(3)), MESES[encontrado.group(2)], int(encontrado.group(1)))


def _funciones(datos: dict, ahora: datetime) -> list[Funcion]:
    funciones = []
    for show in datos.get("shows") or []:
        cuando = show.get("date") or show.get("startDate") or show.get("dateTime")
        if not cuando:
            continue
        inicio = datetime.fromisoformat(cuando.replace("Z", "+00:00")).astimezone(ahora.tzinfo)
        funciones.append(Funcion(inicio=inicio, agotada=show.get("soldOut") is True))
    if not funciones and (dia := _fecha_de_texto(datos.get("description"))):
        funciones.append(Funcion(inicio=datetime.combine(dia, time(0, 0), tzinfo=ahora.tzinfo), sin_hora=True))
    return [f for f in funciones if f.inicio.date() >= ahora.date()]


def armar_evento(datos: dict, ahora: datetime) -> EventoCrudo | None:
    titulo = (datos.get("name") or "").strip()
    if not titulo or esta_cancelado(titulo):
        return None
    lugar = datos.get("venue") or {}
    direccion = lugar.get("address") or {}
    lat, lon = direccion.get("latitude"), direccion.get("longitude")
    if not en_montevideo(lat, lon):
        return None
    funciones = _funciones(datos, ahora)
    if not funciones:
        return None
    url = f"{BASE}/event/{datos['link']}"
    descripcion = texto_plano(datos.get("longDescription")) if datos.get("longDescription") not in (None, "null") else ""
    categoria = GENEROS.get(sin_tildes(datos.get("category") or ""))
    calle = " ".join(str(p) for p in (direccion.get("street"), direccion.get("streetNumber")) if p)
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=str(datos["id"]),
        url=url,
        titulo=titulo,
        categoria=categoria or clasificar(titulo, descripcion, por_defecto="musica"),
        categoria_segura=bool(categoria),
        descripcion_corta=recortar(descripcion),
        lugar=LugarCrudo(nombre=(lugar.get("name") or "").strip(), direccion=calle or None, lat=lat, lon=lon),
        funciones=funciones,
        entradas=[Entrada(url=url, via=NOMBRE)],
        imagen_url=datos.get("thumbImage") or datos.get("image") or None,
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for slug in slugs_de_portada(cliente.texto(f"{BASE}/")):
        try:
            datos = datos_de_ficha(cliente.texto(f"{BASE}/event/{slug}"))
            evento = armar_evento(datos, ahora) if datos else None
        except Exception as error:  # noqa: BLE001 - una ficha rota no frena el resto
            errores.append(f"{slug}: {type(error).__name__}: {error}")
            continue
        if evento:
            eventos.append(evento)
    return eventos, errores
