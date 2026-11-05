"""Eventos que mandan sus organizadores por el formulario "Agregá tu evento" (Tally o Google Forms).

Nada entra sin aprobación: las respuestas caen en una planilla, se aprueban a mano, y una pestaña aparte muestra
solo lo aprobado y sin el contacto de quien lo mandó. Esa pestaña se publica como CSV (ver
`config/agrega_tu_evento.toml`) y esta fuente la lee. Las columnas se reconocen por su encabezado (la pregunta del
formulario), así que se pueden reordenar.

Sin eventos aprobados la fuente queda vacía, y eso no es una falla (`PUEDE_ESTAR_VACIA`).
"""

import csv
import hashlib
import io
import re
import tomllib
from datetime import date, datetime, time
from pathlib import Path

from cartelera.extraer import fecha_sin_anio, precio_de, recortar, texto_plano
from cartelera.geo import menciona_otra_ciudad, sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo

NOMBRE = "propuestos"
CONFIG = Path("config/agrega_tu_evento.toml")
PUEDE_ESTAR_VACIA = True
# Encabezado de la columna (sin tildes, en minúsculas) -> campo. Gana la primera palabra clave que aparece.
# El orden importa: "Otras fechas y horas" o "Si hay más de una fecha…" no son "fecha" ni "hora", y "Nombre de la
# sala" no es el título.
COLUMNAS = [
    ("marca temporal", "enviado"), ("submitted at", "enviado"), ("otras", "otras"), ("mas de una", "otras"), ("direcci", "direccion"), ("sala", "lugar"),
    ("lugar", "lugar"), ("nombre", "titulo"), ("tipo", "tipo"), ("fecha", "fecha"), ("hora", "hora"),
    ("precio", "precio"), ("link", "link"), ("enlace", "link"), ("descrip", "descripcion"), ("aprobado", "aprobado"),
]
# Si la pestaña pública trae la columna "Aprobado", solo pasan las filas tildadas: un segundo control, por si la
# fórmula de la planilla filtra mal.
_TILDADO = {"true", "verdadero", "si", "sí", "x", "1"}
TIPOS = {
    "musica": "musica", "teatro": "teatro", "danza": "danza", "humor": "humor", "stand": "humor", "cine": "cine",
    "exposicion": "exposicion", "muestra": "exposicion", "infantil": "infantil", "chicos": "infantil",
    "fiesta": "fiesta", "festival": "festival", "carnaval": "carnaval", "charla": "charla", "taller": "taller",
    "recorrido": "tour", "visita": "tour",
}
VIAS = {
    "redtickets.uy": "redtickets", "tickantel.com.uy": "tickantel", "passline.com": "passline",
    "mientrada.com.uy": "mientrada", "cobraticket.uy": "cobraticket", "entradasfans.com": "entradasfans",
    "instagram.com": "instagram",
}
_FECHA = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
_HORA = re.compile(r"\b(\d{1,2})[:.](\d{2})\b|\b(\d{1,2})\s*(?:h|hs|horas)\b")


def configuracion(ruta: Path = CONFIG) -> dict:
    return tomllib.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}


def _campo(encabezado: str) -> str | None:
    plano = sin_tildes(encabezado).lower()
    return next((campo for clave, campo in COLUMNAS if clave in plano), None)


def filas(texto_csv: str) -> list[dict[str, str]]:
    """Las filas del CSV con los campos que usa la cartelera (las columnas desconocidas se ignoran)."""
    lector = csv.reader(io.StringIO(texto_csv))
    encabezados = [_campo(e) for e in next(lector, [])]
    resultado = []
    for fila in lector:
        datos: dict[str, str] = {}
        for campo, valor in zip(encabezados, fila):
            if campo and valor.strip() and campo not in datos:
                datos[campo] = valor.strip()
        if "aprobado" in encabezados and datos.get("aprobado", "").strip().lower() not in _TILDADO:
            continue
        if datos.get("titulo"):
            resultado.append(datos)
    return resultado


def leer_fecha(texto: str, hoy: date) -> date | None:
    """'2026-11-20', '20/11/2026' o '20/11' (sin año: la próxima vez que cae)."""
    encontrado = _FECHA.search(texto or "")
    if not encontrado:
        return None
    anio, mes, dia, dia2, mes2, anio2 = encontrado.groups()
    try:
        if anio:
            return date(int(anio), int(mes), int(dia))
        if anio2:
            return date(int(anio2) + (2000 if len(anio2) == 2 else 0), int(mes2), int(dia2))
    except ValueError:
        return None
    return fecha_sin_anio(int(dia2), int(mes2), hoy)


def leer_hora(texto: str) -> time | None:
    encontrado = _HORA.search(texto or "")
    if not encontrado:
        return None
    hora = int(encontrado.group(1) or encontrado.group(3))
    minutos = int(encontrado.group(2) or 0)
    return time(hora, minutos) if hora < 24 and minutos < 60 else None


def funciones(datos: dict, ahora: datetime) -> list[Funcion]:
    """La fecha principal y las otras ("21/11 20:30", una por renglón o separadas por coma o punto y coma)."""
    pares = [(datos.get("fecha", ""), datos.get("hora", ""))]
    pares += [(parte, parte) for parte in re.split(r"[\n;,]+", datos.get("otras", "")) if parte.strip()]
    resultado = {}
    for texto_fecha, texto_hora in pares:
        dia = leer_fecha(texto_fecha, ahora.date())
        if not dia or dia < ahora.date():
            continue
        hora = leer_hora(texto_hora)
        inicio = datetime.combine(dia, hora or time(0, 0), tzinfo=ahora.tzinfo)
        resultado[inicio] = Funcion(inicio=inicio, sin_hora=hora is None)
    return [resultado[k] for k in sorted(resultado)]


def _link(texto: str) -> str | None:
    texto = texto.strip()
    if not texto:
        return None
    if not texto.lower().startswith(("http://", "https://")):
        texto = "https://" + texto.lstrip("/")
    return texto if re.match(r"https?://[\w.-]+\.[a-z]{2,}", texto, re.I) else None


def via_de(url: str) -> str:
    return next((via for dominio, via in VIAS.items() if dominio in url), NOMBRE)


def armar_evento(datos: dict, ahora: datetime) -> EventoCrudo | None:
    titulo = texto_plano(datos.get("titulo"))
    lugar = texto_plano(datos.get("lugar"))
    direccion = texto_plano(datos.get("direccion")) or None
    url = _link(datos.get("link", ""))
    if not titulo or not lugar or not url:
        return None
    if menciona_otra_ciudad(lugar) or (direccion and menciona_otra_ciudad(direccion)):
        return None
    lista = funciones(datos, ahora)
    if not lista:
        return None
    tipo = sin_tildes(datos.get("tipo", "")).lower()
    categoria = next((c for clave, c in TIPOS.items() if clave in tipo), "otros")
    precio = datos.get("precio", "")
    # El id no cambia aunque se corrija la fila: sale de cuándo se mandó y del título original.
    id_externo = hashlib.sha1(f"{datos.get('enviado', '')}|{titulo}".encode()).hexdigest()[:12]
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=id_externo,
        url=url,
        titulo=titulo,
        categoria=categoria,
        categoria_segura=categoria != "otros",
        descripcion_corta=recortar(datos.get("descripcion")),
        lugar=LugarCrudo(nombre=lugar, direccion=direccion),
        funciones=lista,
        # "Gratis", "$500" o "$400 anticipadas - $500 en puerta".
        precio=precio_de(precio if "$" in precio or re.search(r"grat|libre", precio, re.I) else f"$ {precio}")
        if precio else None,
        entradas=[Entrada(url=url, via=via_de(url))],
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    direccion_csv = configuracion().get("csv", "").strip()
    if not direccion_csv:
        return [], []  # el formulario todavía no está armado
    eventos, errores = [], []
    for datos in filas(cliente.texto(direccion_csv)):
        try:
            armado = armar_evento(datos, ahora)
        except Exception as error:  # noqa: BLE001 - una fila rara no frena las demás
            errores.append(f"{datos.get('titulo')}: {type(error).__name__}: {error}")
            continue
        if armado:
            eventos.append(armado)
        elif not (datos.get("lugar") and _link(datos.get("link", "")) and leer_fecha(datos.get("fecha", ""), ahora.date())):
            # Un evento que ya pasó no es un error; uno aprobado al que le falta algo, sí (para revisarlo).
            errores.append(f"{datos.get('titulo')}: falta la sala, el link o una fecha que se entienda")
    return eventos, errores
