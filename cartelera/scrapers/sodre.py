"""Sodre: el calendario de su web se alimenta de un endpoint JSON con cada función (inicio y fin).

La sala sale de la API de WordPress (taxonomía `lugar`). Casi todo se vende por Tickantel y cada
espectáculo enlaza a su página ahí, así que el cruce con Tickantel es exacto.
"""

import html
import logging
import re
from datetime import datetime, timedelta

from cartelera.categorias import categoria_por_lugar, clasificar, esta_cancelado
from cartelera.extraer import recortar
from cartelera.geo import sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo

NOMBRE = "sodre"
BASE = "https://sodre.gub.uy/espectaculos"
MESES_ADELANTE = 8
MARGEN_PASADO = timedelta(hours=6)
# Elencos estables del Sodre traducidos a nuestras categorías.
CATEGORIA_POR_ELENCO = {
    "ballet nacional": "danza", "orquesta": "musica", "coro": "musica", "musica de camara": "musica",
    "cine": "cine", "carnaval": "carnaval",
}
log = logging.getLogger(__name__)


def _categoria(elencos: list[str], titulo: str, resumen: str, lugar: str) -> tuple[str, bool]:
    """(categoría, si viene de la fuente). Los elencos estables definen la categoría con seguridad."""
    for elenco in map(sin_tildes, elencos):
        for clave, categoria in CATEGORIA_POR_ELENCO.items():
            if clave in elenco:
                return categoria, True
    return clasificar(titulo, resumen, por_defecto=categoria_por_lugar(lugar)), False


def funciones_del_calendario(datos: list[dict], ahora: datetime) -> dict[int, list[dict]]:
    """{id del espectáculo: [funciones del calendario]}, solo las que no pasaron."""
    por_espectaculo: dict[int, list[dict]] = {}
    for item in datos:
        if not item.get("start"):
            continue
        inicio = datetime.fromisoformat(item["start"]).replace(tzinfo=ahora.tzinfo)
        if inicio < ahora - MARGEN_PASADO:
            continue
        por_espectaculo.setdefault(item["extendedProps"]["id"], []).append(item)
    return por_espectaculo


def armar_evento(items: list[dict], lugar: str, ahora: datetime) -> EventoCrudo | None:
    primero = items[0]
    extra = primero["extendedProps"]
    titulo = html.unescape(primero["title"]).strip()
    if esta_cancelado(titulo):
        return None
    elencos = [html.unescape(e["name"]) for e in extra.get("elencoEstablesData") or []]
    resumen = html.unescape(extra.get("resumen") or "")
    categoria, segura = _categoria(elencos, titulo, resumen, lugar)
    funciones = []
    for item in items:
        inicio = datetime.fromisoformat(item["start"]).replace(tzinfo=ahora.tzinfo)
        fin = datetime.fromisoformat(item["end"]).replace(tzinfo=ahora.tzinfo) if item.get("end") else None
        funciones.append(Funcion(inicio=inicio, fin=fin if fin and fin > inicio else None))
    compra = extra.get("enlace_de_compra") or ""
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=str(extra["id"]),
        url=primero["url"],
        titulo=titulo,
        categoria=categoria,
        categoria_segura=segura,
        descripcion_corta=recortar(resumen),
        lugar=LugarCrudo(nombre=lugar),
        funciones=sorted(funciones, key=lambda f: f.inicio),
        entradas=[Entrada(url=compra, via="tickantel" if "tickantel" in compra else "sodre")] if compra else [],
        imagen_url=extra.get("foto_miniatura") or None,
        # El elenco estable va como productor: así se detecta, por ejemplo, el Ballet Nacional del Sodre.
        productor=", ".join(f"{e} del Sodre" if "sodre" not in e.lower() else e for e in elencos) or "Sodre",
        enlaces=[compra] if compra else [],
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    pagina = cliente.texto(f"{BASE}/calendario")
    nonce = re.search(r'nonce["\']?\s*[:=]\s*["\']([a-f0-9]{8,})', pagina)
    if not nonce:
        raise RuntimeError("no se encontró el token del calendario del Sodre")
    hasta = (ahora + timedelta(days=31 * MESES_ADELANTE)).date().isoformat()
    respuesta = cliente.get(
        f"{BASE}/wp-admin/admin-ajax.php?action=Calendar&nonce={nonce.group(1)}&s=&from={ahora.date().isoformat()}&to={hasta}"
    ).json()
    por_espectaculo = funciones_del_calendario(respuesta.get("data") or [], ahora)
    log.info("sodre: %s espectáculos con funciones próximas", len(por_espectaculo))
    if not por_espectaculo:
        return [], []

    # Sala de cada espectáculo, en un solo pedido a la API de WordPress.
    ids = ",".join(map(str, por_espectaculo))
    fichas = cliente.get(f"{BASE}/wp-json/wp/v2/espectaculo?include={ids}&per_page=100&_fields=id,lugar").json()
    lugares = {l["id"]: html.unescape(l["name"]) for l in cliente.get(f"{BASE}/wp-json/wp/v2/lugar?per_page=100").json()}
    lugar_de = {f["id"]: lugares.get((f.get("lugar") or [None])[0]) for f in fichas}

    eventos, errores = [], []
    for id_espectaculo, items in por_espectaculo.items():
        try:
            evento = armar_evento(items, lugar_de.get(id_espectaculo) or "Auditorio Nacional Adela Reta", ahora)
        except Exception as error:  # noqa: BLE001 - un espectáculo roto no frena el resto
            errores.append(f"{id_espectaculo}: {type(error).__name__}: {error}")
            continue
        if evento:
            eventos.append(evento)
    return eventos, errores
