"""Corchea.uy: la cartelera de música en vivo de un sitio de música uruguaya (y de su sala, Sala Corchea).

Su robots.txt es estricto: un pedido por minuto, como mucho 6 por hora, y solo de 00:00 a 09:00 (hora de
Buenos Aires, la misma que Montevideo). Por eso esta fuente hace **un solo pedido por día**: el feed RSS de la
categoría Cartelera, que trae los ~50 avisos más nuevos completos, y solo en la corrida de la madrugada
(`HORARIO`); en las otras corridas del día se queda con lo que trajo esa.

Cada aviso se titula "04/11 – Artista" y trae los datos en campos: "Fecha: 04/11/2026", "Hora: 21:00",
"Lugar: Sala Corchea", a veces "Dirección", el precio y el link de venta. Muchos se venden por Tickantel o
RedTickets, y ese link los une con el mismo evento de la ticketera.
"""

import html
import re
from datetime import date, datetime, time

from cartelera.categorias import es_deporte, esta_cancelado
from cartelera.extraer import precio_de, recortar, texto_plano
from cartelera.geo import menciona_otra_ciudad
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo
from cartelera.scrapers.ladiaria import items_del_feed

NOMBRE = "corchea"
FEED = "https://corchea.uy/category/cartelera/feed/"
HORARIO = (time(0, 0), time(9, 0))  # el Visit-time de su robots.txt, en hora de Montevideo
# Salas de su cartelera que no son de Montevideo.
FUERA_DE_MONTEVIDEO = re.compile(r"politeama|centro cultural de pando|maccio|escayola", re.I)
_CAMPO = re.compile(
    r"(Fecha|Hora|Lugar|Direcci[oó]n|Precio de las entradas|Entradas Online)\s*:\s*"
    r"(.*?)(?=(?:Fecha|Hora|Lugar|Direcci[oó]n|Precio de las entradas|Entradas Online|Formas de Pago|Pago web|"
    r"Condiciones especiales)\s*:|$)",
    re.S,
)
# "04/11/2026" o "12 y 13/11/2026".
_FECHA = re.compile(r"((?:\d{1,2}\s*(?:,|y)\s*)*\d{1,2})/(\d{1,2})/(\d{4})")
_FECHA_TITULO = re.compile(r"^\s*((?:\d{1,2}\s*(?:,|y)\s*)*\d{1,2})/(\d{1,2})\s*[–-]+\s*")
_HORA = re.compile(r"(\d{1,2})[:.](\d{2})")
_VENTA = re.compile(
    r'href="(https?://(?:www\.)?(?:tickantel\.com\.uy|redtickets\.uy|passline\.com|entradasfans\.com|'
    r'mientrada\.com\.uy|cobraticket\.uy)/[^"]+)"'
)
VIAS = {"tickantel": "tickantel", "redtickets": "redtickets", "passline": "passline",
        "entradasfans": "entradasfans", "mientrada": "mientrada", "cobraticket": "cobraticket"}


def puede_correr(ahora: datetime) -> bool:
    return HORARIO[0] <= ahora.time() < HORARIO[1]


def _dias(texto: str) -> list[int]:
    return [int(d) for d in re.findall(r"\d{1,2}", texto)]


def _campos(texto: str) -> dict[str, str]:
    campos = {}
    for nombre, valor in _CAMPO.findall(texto):
        campos.setdefault(nombre.replace("ó", "o"), valor.strip(" .|"))
    return campos


def _via(url: str) -> str:
    return next((via for clave, via in VIAS.items() if clave in url), NOMBRE)


def armar_evento(item: dict, ahora: datetime) -> EventoCrudo | None:
    titulo_aviso = item["titulo"]
    texto = texto_plano(item["html"])
    campos = _campos(texto)
    fecha = _FECHA.search(campos.get("Fecha", ""))
    lugar = campos.get("Lugar", "")
    del_titulo = _FECHA_TITULO.match(titulo_aviso)
    if not fecha or not lugar or not del_titulo:
        return None
    titulo = titulo_aviso[del_titulo.end():].strip()
    if (
        esta_cancelado(titulo) or es_deporte(titulo) or FUERA_DE_MONTEVIDEO.search(lugar)
        or menciona_otra_ciudad(titulo) or menciona_otra_ciudad(lugar)
    ):
        return None
    dias, mes, anio = _dias(fecha.group(1)), int(fecha.group(2)), int(fecha.group(3))
    # A veces el aviso se copia de otro y queda con la fecha vieja en un lado: si no coinciden, no se adivina.
    if _dias(del_titulo.group(1)) != dias or int(del_titulo.group(2)) != mes:
        return None
    hora = _HORA.search(campos.get("Hora", ""))
    hora = time(int(hora.group(1)), int(hora.group(2))) if hora else None
    funciones = []
    for dia in dias:
        try:
            fecha_funcion = date(anio, mes, dia)
        except ValueError:
            continue
        if fecha_funcion >= ahora.date():
            funciones.append(Funcion(
                inicio=datetime.combine(fecha_funcion, hora or time(0, 0), tzinfo=ahora.tzinfo), sin_hora=hora is None,
            ))
    if not funciones:
        return None
    # Un solo link de venta: si hay varios, alguno puede ser de otro show (copiado de otro aviso) y uniría mal.
    ventas = list(dict.fromkeys(html.unescape(v) for v in _VENTA.findall(item["html"])))
    entradas = [Entrada(url=ventas[0], via=_via(ventas[0]))] if len(ventas) == 1 else []
    descripcion = texto.split("Fecha:")[0]
    precio = campos.get("Precio de las entradas") or campos.get("Entradas Online") or ""
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=item["id"],
        url=item["url"],
        titulo=titulo,
        # Es una cartelera de música: las palabras sueltas ("candombe", "jazz cartoons") no la vuelven otra cosa.
        categoria="musica",
        descripcion_corta=recortar(descripcion),
        lugar=LugarCrudo(nombre=lugar, direccion=campos.get("Direccion") or None),
        funciones=funciones,
        # "Entradas Generales: $590 | PROMO 2×1: $905": cada parte separada por "|" es una tarifa.
        precio=precio_de(precio.replace("|", ";")) if precio else None,
        entradas=entradas + [Entrada(url=item["url"], via=NOMBRE)],
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for item in items_del_feed(cliente.texto(FEED)):
        try:
            armado = armar_evento(item, ahora)
        except Exception as error:  # noqa: BLE001 - un aviso raro no frena los demás
            errores.append(f"{item.get('url')}: {type(error).__name__}: {error}")
            continue
        if armado:
            eventos.append(armado)
    return eventos, errores
