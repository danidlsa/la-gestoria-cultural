"""CobraTicket: ticketera de fiestas y boliches, que también vende congresos y partidos.

El sitio está hecho con SvelteKit, que publica los datos de cada página en `<página>/__data.json`. El de
`/eventos` trae los próximos eventos (nombre, fecha, categoría, sala, imagen); el de cada evento suma la
descripción y la sala con dirección y coordenadas. Se dejan afuera los congresos, el deporte y lo que no es en
Montevideo (hay mucho de Punta del Este en verano).

Los datos vienen en el formato de SvelteKit ("devalue"): una lista plana donde cada objeto guarda, en vez de sus
valores, la posición de cada valor en la lista.
"""

import json
from datetime import datetime

from cartelera.categorias import clasificar, es_deporte, esta_cancelado
from cartelera.extraer import recortar, texto_plano
from cartelera.geo import en_montevideo
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo

NOMBRE = "cobraticket"
BASE = "https://cobraticket.uy"
CATEGORIAS_AFUERA = {"congresos", "deportes"}
CATEGORIAS = {"fiestas": "fiesta", "teatro": "teatro", "musica": "musica", "música": "musica", "humor": "humor"}


def desarmar(datos: list, indice: int = 0):
    """Arma el valor en `indice` de una lista "devalue" de SvelteKit (los negativos son undefined/null)."""
    if indice < 0:
        return None
    valor = datos[indice]
    if isinstance(valor, dict):
        return {clave: desarmar(datos, i) for clave, i in valor.items()}
    if isinstance(valor, list):
        return [desarmar(datos, i) for i in valor]
    return valor


def datos_de_pagina(texto: str) -> dict:
    """Los datos propios de la página (el último nodo con datos de `__data.json`)."""
    nodos = [n for n in json.loads(texto)["nodes"] if n and n.get("type") == "data"]
    return desarmar(nodos[-1]["data"])


def _fecha(texto: str, ahora: datetime) -> datetime:
    return datetime.fromisoformat(texto).replace(tzinfo=ahora.tzinfo)


def armar_evento(datos: dict, ahora: datetime) -> EventoCrudo | None:
    evento = datos["props"]
    titulo = texto_plano(evento.get("name"))
    categoria_fuente = ((evento.get("category") or {}).get("name") or "").strip().lower()
    descripcion = texto_plano(evento.get("description"))
    if (
        not titulo or not evento.get("startAt") or esta_cancelado(titulo) or evento.get("status") != "PUBLISHED"
        or categoria_fuente in CATEGORIAS_AFUERA or es_deporte(titulo)
    ):
        return None
    lugar = evento.get("location") or {}
    punto = lugar.get("latlng") or {}
    lat, lon = punto.get("lat"), punto.get("lng")
    if lat is None or not en_montevideo(lat, lon):
        return None
    # Una misma página puede tener varias funciones (otras fechas del mismo evento).
    fechas = [evento] + [f for f in (evento.get("relatedFunctions") or []) if isinstance(f, dict)]
    funciones = []
    for f in fechas:
        if not f.get("startAt"):
            continue
        inicio = _fecha(f["startAt"], ahora)
        fin = _fecha(f["endAt"], ahora) if f.get("endAt") else None
        if inicio.date() >= ahora.date():
            funciones.append(Funcion(inicio=inicio, fin=fin if fin and fin > inicio else None))
    if not funciones:
        return None
    url = f"{BASE}/e/{evento['slug']}"
    categoria = CATEGORIAS.get(categoria_fuente)
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=str(evento.get("code") or evento["slug"]),
        url=url,
        titulo=titulo,
        categoria=categoria or clasificar(titulo, descripcion, por_defecto="fiesta"),
        categoria_segura=categoria is not None,
        descripcion_corta=recortar(descripcion),
        lugar=LugarCrudo(
            nombre=texto_plano(lugar.get("name")), direccion=texto_plano(lugar.get("address")) or None, lat=lat, lon=lon,
        ),
        funciones=sorted(funciones, key=lambda f: f.inicio),
        entradas=[Entrada(url=url, via=NOMBRE)],
        imagen_url=(evento.get("image") or {}).get("url"),
        productor=texto_plano((evento.get("account") or {}).get("name")) or None,
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    proximos = datos_de_pagina(cliente.texto(f"{BASE}/eventos/__data.json")).get("nextEvents") or []
    eventos, errores = [], []
    for item in proximos:
        if ((item.get("category") or {}).get("name") or "").strip().lower() in CATEGORIAS_AFUERA:
            continue  # no hace falta ni pedir la ficha
        try:
            armado = armar_evento(datos_de_pagina(cliente.texto(f"{BASE}/e/{item['slug']}/__data.json")), ahora)
        except Exception as error:  # noqa: BLE001 - una ficha rota no frena las demás
            errores.append(f"{item.get('slug')}: {type(error).__name__}: {error}")
            continue
        if armado:
            eventos.append(armado)
    return eventos, errores
