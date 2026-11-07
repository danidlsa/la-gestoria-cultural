"""Programas de los eventos especiales publicados como mapa de Google (Google My Maps).

La Intendencia publica la Noche de las Librerías como un mapa: un punto por librería con su dirección, su barrio
y sus actividades ("19:00 h | Narrativas del miedo: terror y suspenso…"). Google deja bajar cada mapa público
como KML (la dirección /maps/d/ está permitida en su robots.txt). Cada actividad pasa a ser un evento, con la
librería como sala y el especial como ciclo, así aparece en su pestaña, en la agenda, en el mapa y en Mi plan.

Qué mapa leer está en config/eventos_especiales.toml: el especial lleva `mapa` (el `mid` del mapa), `desde` (el
día), `horario` (de qué hora a qué hora es la noche) y `pagina` (la página oficial, que es el enlace de cada
actividad). Se leen solo los que todavía no pasaron.

Los puntos los carga cada librería y no siempre igual: las actividades vienen en dos campos que a veces no
coinciden (a uno le falta la primera, el otro trae una más), así que se juntan los dos sin repetir. Lo que no
tiene hora ("Durante la noche: feria de libros") queda como una actividad de toda la noche.
"""

from rapidfuzz import fuzz

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, time, timedelta

from cartelera import especiales
from cartelera.categorias import esta_cancelado
from cartelera.extraer import recortar, texto_plano
from cartelera.geo import sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo

NOMBRE = "mapas_especiales"
PUEDE_ESTAR_VACIA = True  # fuera de temporada no hay ningún especial con mapa
KML = "https://www.google.com/maps/d/kml?mid={mid}&forcekml=1"
_K = "{http://www.opengis.net/kml/2.2}"

# "19:00 h |", "18:30 a 01:00 h |", "19.30 hs |", "20:30 |": el comienzo de cada actividad.
_HORA = re.compile(r"(\d{1,2})[:.](\d{2})(?:\s*(?:a|-|–)\s*(\d{1,2})[:.](\d{2}))?\s*(?:h(?:s|oras)?\.?)?\s*\|\s*", re.I)
# Lo que no tiene hora y vale para toda la noche ("Durante la noche: propuesta gastronómica…").
_TODA_LA_NOCHE = re.compile(r"\s*(Durante (?:toda )?la noche|Toda la noche)\s*:\s*", re.I)
_ARRANQUE_NOCHE = re.compile(r"^(?:Durante (?:toda )?la noche|Toda la noche)[\s,:]*(?:(?:est[aá]n?|hay|habr[aá]|se puede[n]?)\s+)?", re.I)
# Títulos que solos no dicen nada: se completan con la primera frase de la descripción.
_GENERICOS = {"charla", "mesa", "taller", "presentacion", "musica", "musica en vivo", "lectura", "lecturas", "actividad", "actividades"}
# Una actividad que arranca antes de esta hora es de la madrugada siguiente ("01:00 h").
_MADRUGADA = 6


def _datos(lugar: ET.Element) -> dict[str, str]:
    """Los campos del punto ("Dirección", "Barrio", "Actividades"…), por nombre sin tildes ni mayúsculas."""
    campos: dict[str, str] = {}
    for dato in lugar.iter(f"{_K}Data"):
        valor = (dato.findtext(f"{_K}value") or "").strip()
        clave = sin_tildes(dato.get("name") or "").strip().lower()
        if valor and len(valor) > len(campos.get(clave, "")):
            campos[clave] = valor
    return campos


def _campo(texto: str, nombre: str) -> str:
    """Un campo dentro del texto de "descripción" ("Actividades: … Participantes: …")."""
    encontrado = re.search(rf"(?:^|\n){nombre}:\s*(.*?)(?=\n(?:Direcci[oó]n|Barrio|Actividades|Participantes):|\Z)", texto, re.S | re.I)
    return encontrado.group(1).strip() if encontrado else ""


def separar_actividades(texto: str) -> tuple[list[dict], str]:
    """Las actividades con su hora, y lo que vale para toda la noche (sin hora)."""
    texto = re.sub(r"\s+", " ", texto or "").strip()
    nota = ""
    resto = _TODA_LA_NOCHE.split(texto, maxsplit=1)
    if len(resto) == 3:
        texto, nota = resto[0].strip(), resto[2].strip()
    marcas = list(_HORA.finditer(texto))
    if not marcas:  # nada con hora: todo el texto es "de toda la noche"
        return [], " ".join(x for x in (texto, nota) if x)
    actividades = []
    for i, marca in enumerate(marcas):
        fin_texto = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        cuerpo = texto[marca.end():fin_texto].strip()
        if not cuerpo:
            continue
        h, m, h2, m2 = marca.groups()
        actividades.append({
            "inicio": time(int(h) % 24, int(m)),
            "fin": time(int(h2) % 24, int(m2)) if h2 else None,
            "texto": cuerpo,
        })
    return actividades, nota


def titulo_y_detalle(texto: str) -> tuple[str, str]:
    """'Noche de jazz. Presentación musical…' -> ('Noche de jazz', 'Presentación musical…').

    El título es lo que va antes del primer punto, de los dos puntos o de un signo de pregunta o exclamación
    que cierra; si queda muy largo, se corta y la descripción lleva el texto entero.
    """
    corte = re.search(r"(?<=.{3})(?:([?!])|[.:])\s", texto)
    if corte and corte.start() <= 110:
        titulo = texto[:corte.start()] + (corte.group(1) or "")
        detalle = texto[corte.end():].strip()
    else:
        titulo, detalle = texto.rstrip(". "), ""
    titulo = titulo.strip()
    if len(titulo) > 90:
        titulo, detalle = recortar(titulo, 90), texto
    return titulo, detalle


def _sin_generico(titulo: str, detalle: str, nombres: set[str]) -> tuple[str, str]:
    """'Charla' + 'El libro de terror en Uruguay. Un encuentro…' -> 'Charla: El libro de terror en Uruguay'."""
    clave = sin_tildes(titulo).lower().strip(" .")
    if detalle and (clave in _GENERICOS or clave in nombres):
        siguiente, detalle = titulo_y_detalle(detalle)
        titulo = siguiente if clave in nombres else f"{titulo}: {siguiente}"
    return titulo, detalle


_MUSICA = re.compile(r"\b(musica|musical|recital|concierto|banda|dj|vinilos?|coro|tango|blues|rock|cantante|canciones)\b")


def tipo_de_actividad(titulo: str, detalle: str) -> str:
    """Pocos tipos y claros: casi todo es una charla o una presentación de libro."""
    todo = sin_tildes(f"{titulo} {detalle}").lower()
    if re.search(r"\b(ninas?|ninos?|infancias?|familias?|infantil|cuentacuentos|pintacaritas|titeres)\b", todo):
        return "infantil"
    if re.search(r"\btaller", todo):
        return "taller"
    # Música si lo dice el título, o si la descripción es de un show ("Presentación musical", "Recital…"), no de un libro.
    if _MUSICA.search(sin_tildes(titulo).lower()) or (
        re.search(r"^(presentacion musical|recital|musica|show)|cierre musical", sin_tildes(detalle).lower())
    ):
        return "musica"
    if re.search(r"\b(exposicion|muestra)\b", todo):
        return "exposicion"
    return "charla"


def _juntar(listas: list[list[dict]]) -> list[dict]:
    """Las actividades de los dos campos, sin repetir las que están en ambos (misma hora, título parecido)."""
    juntas: list[dict] = []
    for lista in sorted(listas, key=len, reverse=True):
        for actividad in lista:
            repetida = any(
                otra["inicio"] == actividad["inicio"]
                and fuzz.partial_ratio(sin_tildes(otra["texto"][:60]).lower(), sin_tildes(actividad["texto"][:60]).lower()) >= 70
                for otra in juntas
            )
            if not repetida:
                juntas.append(actividad)
    return sorted(juntas, key=lambda a: (a["inicio"].hour < _MADRUGADA, a["inicio"]))


def _a_fecha(dia: date, hora: time, zona) -> datetime:
    # Lo de la madrugada (antes de las 6) es del día siguiente: la noche del viernes termina el sábado a la 1.
    return datetime.combine(dia + timedelta(days=1 if hora.hour < _MADRUGADA else 0), hora, tzinfo=zona)


def _hora(texto: str) -> time:
    h, m = texto.split(":")
    return time(int(h), int(m))


def eventos_del_mapa(kml: str, especial: dict, anio: int, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    raiz = ET.fromstring(kml)
    dia: date = especial["desde"]
    ciclo = f"{especial['nombre']} {anio}"
    abre, cierra = (_hora(h) for h in especial.get("horario", ["19:00", "01:00"]))
    genericos = {sin_tildes(especial["nombre"]).lower(), sin_tildes(re.sub(r"^La ", "", especial["nombre"])).lower()}
    genericos |= {f"{g} {anio}" for g in genericos}
    eventos, errores = [], []
    for punto in raiz.iter(f"{_K}Placemark"):
        nombre = texto_plano(punto.findtext(f"{_K}name") or "")
        datos = _datos(punto)
        descripcion = datos.get("descripcion", "")
        direccion = punto.findtext(f"{_K}address") or datos.get("direccion") or _campo(descripcion, "Direcci[oó]n")
        direccion = re.sub(r",\s*Montevideo,\s*Uruguay\s*$", "", (direccion or "").strip(), flags=re.I) or None
        barrio = datos.get("barrio") or _campo(descripcion, "Barrio") or None
        # Las actividades vienen en dos campos ("Actividades" y dentro de "descripción") que no siempre coinciden.
        separadas = [separar_actividades(c) for c in (_campo(descripcion, "Actividades"), datos.get("actividades", ""))]
        actividades = _juntar([a for a, _ in separadas])
        notas = list(dict.fromkeys(n for _, n in separadas if n))
        for nota in notas[:1]:  # lo de toda la noche, una vez (los dos campos lo repiten con otras palabras)
            texto = _ARRANQUE_NOCHE.sub("", nota).strip()
            if texto:
                actividades.append({"inicio": abre, "fin": cierra, "texto": texto[0].upper() + texto[1:]})
        participantes = datos.get("participantes") or _campo(descripcion, "Participantes")
        coordenadas = (punto.findtext(f".//{_K}coordinates") or "").strip()
        lat = lon = None
        if coordenadas:
            lon, lat = (float(x) for x in coordenadas.split(",")[:2])
        if not nombre or not actividades:
            if nombre:
                errores.append(f"{nombre}: sin actividades con hora")
            continue
        lugar = LugarCrudo(nombre=nombre, direccion=direccion, lat=lat, lon=lon, barrio=barrio)
        nombres = genericos | {sin_tildes(nombre).lower()}
        for actividad in actividades:
            titulo, detalle = _sin_generico(*titulo_y_detalle(actividad["texto"]), nombres)
            if esta_cancelado(titulo):
                continue
            inicio = _a_fecha(dia, actividad["inicio"], ahora.tzinfo)
            fin = _a_fecha(dia, actividad["fin"], ahora.tzinfo) if actividad["fin"] else None
            detalle = detalle[:1].upper() + detalle[1:]  # "terror y suspenso…" (venía después de los dos puntos)
            extras = " ".join(x for x in (detalle, f"Participan: {participantes}." if participantes else "") if x)
            eventos.append(EventoCrudo(
                fuente=NOMBRE,
                # Con la hora y el título (y no el orden en la lista): si la Intendencia suma una actividad, las demás
                # conservan su id, y no se pierden de Mi plan ni de los enlaces a recorridos que ya se compartieron.
                id_externo="-".join(re.sub(r"[^a-z0-9]+", "-", sin_tildes(x).lower()).strip("-")[:40] for x in (
                    especial["id"], str(anio), nombre, actividad["inicio"].strftime("%H%M"), titulo)),
                url=especial["pagina"],
                titulo=titulo,
                categoria=tipo_de_actividad(titulo, detalle),
                descripcion_corta=recortar(extras, 400) if extras else None,
                lugar=lugar,
                funciones=[Funcion(inicio=inicio, fin=fin if fin and fin > inicio else None)],
                entradas=[Entrada(url=especial["pagina"], via=NOMBRE)],
                ciclo=ciclo,
            ))
    return eventos, errores


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    if not especiales.activo():
        return [], []
    eventos, errores = [], []
    for especial in especiales.cargar():
        dia = especial.get("desde")
        if not especial.get("mapa") or not dia or especial.get("hasta", dia) < ahora.date():
            continue
        try:
            kml = cliente.texto(KML.format(mid=especial["mapa"]))
            nuevos, problemas = eventos_del_mapa(kml, especial, dia.year, ahora)
        except Exception as error:  # noqa: BLE001 - un mapa roto no frena los demás
            errores.append(f"{especial['id']}: {type(error).__name__}: {error}")
            continue
        eventos += nuevos
        errores += [f"{especial['id']}: {p}" for p in problemas]
    return eventos, errores
