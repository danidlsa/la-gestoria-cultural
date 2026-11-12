"""Bares y salas chicas que programan por Instagram (lista en `config/instagram_bares.toml`).

Lee los posts recientes de cada cuenta con la API oficial de Meta (Business Discovery), con la clave de la página de
de La Gestoría. No se publica nada solo:

1. Un post cuyo texto tiene día y hora que todavía no pasaron queda como **borrador** en
   `datos/instagram/borradores.json`. El reconocimiento es con reglas, sin IA: "sábado 24", "13/11", "13 de
   noviembre", "hoy", "este viernes"… y "21 h", "21:30" o "a las 21".
2. `python -m cartelera avisos --github` abre un aviso en GitHub con los borradores nuevos, uno por renglón y con una
   casilla. GitHub manda un correo (el aviso queda asignado a la dueña del repo).
3. Lo tildado se publica en la corrida siguiente. Si se cambia el título (lo que va entre `**`), se usa ese. Si se
   saca el tilde, se va.

Sin conexión con GitHub (una corrida en el equipo), valen las aprobaciones guardadas en la última corrida buena.
"""

import hashlib
import json
import logging
import os
import re
import subprocess
import tomllib
from datetime import date, datetime, time, timedelta
from pathlib import Path

import httpx
from rapidfuzz import fuzz

from cartelera.categorias import clasificar
from cartelera.extraer import precio_de, recortar
from cartelera.geo import sin_tildes
from cartelera.http import USER_AGENT
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo
from cartelera.scrapers.base import MONTEVIDEO
from cartelera.scrapers.propuestos import guardar_afiche

NOMBRE = "instagram_bares"
PUEDE_ESTAR_VACIA = True  # sin nada aprobado, no hay eventos
CONFIG = Path("config/instagram_bares.toml")
BORRADORES = Path("datos/instagram/borradores.json")
ESTADO = Path("datos/instagram/cuentas.json")  # qué cuentas se pudieron leer en la última corrida
# Para revisar las reglas en el equipo: con IG_GUARDAR_POSTS=1 se guardan los textos de todos los posts leídos.
POSTS_LEIDOS = Path("datos/instagram/posts.json")
DIR_AFICHES = Path("datos/afiches/instagram")  # aparte: propuestos borra los afiches de datos/afiches/ que no son suyos
URL_SITIO = "https://lagestoriacultural.uy/"
GRAPH = "https://graph.facebook.com/v27.0"
POSTS_POR_CUENTA = 25  # alcanza para ver lo que ya está anunciado, aunque el bar publique mucho
ANTIGUEDAD_MAXIMA = timedelta(days=45)  # posts más viejos no se miran (hay quien anuncia con un mes de anticipación)
HORIZONTE = timedelta(days=60)  # una fecha más allá de esto, contada desde el post, es sospechosa
ETIQUETA = "borradores-instagram"
TRANSPORTE = None  # en los tests, respuestas simuladas
log = logging.getLogger(__name__)

# --- Reconocer día y hora en el texto de un post ------------------------------------------------------------------

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
    "ene": 1, "feb": 2, "abr": 4, "jun": 6, "jul": 7, "ago": 8, "sept": 9, "sep": 9, "set": 9, "oct": 10, "nov": 11,
    "dic": 12,
}
DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
_DIA = r"(lunes|martes|miercoles|jueves|viernes|sabado|domingo)"
_MES = "(" + "|".join(sorted(MESES, key=len, reverse=True)) + ")"

# Horarios de apertura y cosas que se repiten no son un evento: "de lunes a viernes", "todos los jueves", "sábados".
# Tampoco un período ("del 20/12 al 5/1", "hasta el 30 de noviembre"): eso es un cierre, una muestra o una promo.
_RECURRENTE = re.compile(
    rf"\b(de\s+)?{_DIA}\s+(a|al|y)\s+{_DIA}\b|\b(todos\s+los|todas\s+las|cada)\s+\w+|\b(sabados|domingos)\b"
    rf"|\b(del?|desde\s+el)\s+\d{{1,2}}(\s*(de\s+|/)\s*{_MES}|/\d{{1,2}})?\s+(al|hasta\s+el)\s+\d{{1,2}}(\s*(de\s+|/)\s*{_MES}|/\d{{1,2}})?"
    rf"|\bhasta\s+el\s+\d{{1,2}}(\s*(de\s+|/)\s*{_MES}|/\d{{1,2}})?"
    rf"|\b\d{{1,2}}\s*(de\s+)?{_MES}\s*[-–]\s*\d{{1,2}}\s*(de\s+)?{_MES}"  # "18 de noviembre - 18 de diciembre"
)
_FECHA_MES = re.compile(rf"\b(\d{{1,2}})\s*(?:de\s+|[/.\-]\s*)?{_MES}\b")  # "13 de noviembre", "04/Noviembre"
_FECHA_BARRA = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
# "jueves 12", y también listas: "miércoles 11 y 18", "lunes 7, 14 y 21" (todos el mismo día de la semana).
_DIA_NUMERO = re.compile(rf"\b{_DIA}\s+(\d{{1,2}}(?:\s*(?:,|\by\b|\be\b)\s*\d{{1,2}}\b(?!\s*[:./h]))*)\b(?!\s*/)")
# "13, 14 y 15 de noviembre": varios días del mismo mes.
_LISTA_MES = re.compile(rf"\b(\d{{1,2}}(?:\s*(?:,|\by\b)\s*\d{{1,2}})+)\s*(?:de\s+)?{_MES}\b")
_DIA_SOLO = re.compile(rf"\b{_DIA}\b(?!\s+\d)")
_HOY = re.compile(r"\b(hoy|esta\s+noche)\b")
_MANANA = re.compile(r"(?<!la )\bmanana\b")  # "mañana", pero no "a la mañana"
_HORA = re.compile(
    r"\b(?:a|desde|de)\s+las\s+(\d{1,2})(?:[:.](\d{2}))?\b"  # "a las 21", "desde las 20.30"
    r"|\b(\d{1,2})[:.](\d{2})\s*(?:h|hs|hrs|horas)\b"  # "20.30 hs"
    r"|\b(\d{1,2}):(\d{2})\b"  # "21:30"
    r"|\b(\d{1,2})(?:[:.](\d{2}))?\s*(?:-|–|a)\s*\d{1,2}(?:[:.]\d{2})?\s*(?:h|hs|hrs|horas)\b"  # "17-22h", "18.30 a 20.30 h": la primera
    r"|\b(\d{1,2})\s*(?:h|hs|hrs|horas)\b"  # "21h", "21 hs"
)
_MEDIODIA = re.compile(r"\bmediodia\b")
# "Martes de noviembre", "todos los jueves de diciembre": un ciclo, todas las fechas de ese día en ese mes.
_SERIE = re.compile(rf"\b(lunes|martes|miercoles|jueves|viernes|sabado|domingo)s?\s+de\s+{_MES}\b")
# Las fechas de un sorteo, un descuento o una vigencia no son de un evento ("Anunciamos ganador el jueves 12/11").
_NO_ES_EVENTO = re.compile(r"ganador|sorteo|sorteamos|participa[rn]?\b|valido|vigente|descuento|vence|fecha limite|postula"
                           r"|convocatoria|inscripciones?\s+(hasta|cierra)|cierre\s+de\s+(inscripciones|postulaciones)")
# Un post que abre con una convocatoria o un llamado ("CONVOCATORIA ABIERTA", "Inscribí tu propuesta") no anuncia un
# evento: sus fechas son de inscripción. Se mira solo el principio, para no perder un evento que la menciona al final.
_CONVOCATORIA = re.compile(r"convocatoria|convocamos|llamado\s+(abierto|a\s)|postula|inscribi\s+tu\s+propuesta"
                           r"|recepcion\s+de\s+(propuestas|postulaciones)")


def _dia_con_numero(numero: int, dia_semana: int | None, desde: date) -> date | None:
    """El próximo día con ese número (este mes o los dos siguientes) que caiga en ese día de la semana, si se dijo.

    "Lunes 14" leído el 11 de noviembre: el 14 de noviembre es sábado, así que es el lunes 14 de diciembre.
    """
    for meses in (0, 1, 2):
        anio, mes = desde.year + (desde.month + meses - 1) // 12, (desde.month + meses - 1) % 12 + 1
        try:
            candidata = date(anio, mes, numero)
        except ValueError:
            continue
        if candidata >= desde and (dia_semana is None or candidata.weekday() == dia_semana):
            return candidata
    return None


def _con_mes(dia: int, mes: int, anio: int | None, desde: date) -> date | None:
    try:
        if anio:
            return date(anio + (2000 if anio < 100 else 0), mes, dia)
        candidata = date(desde.year, mes, dia)
        return candidata if candidata >= desde - timedelta(days=1) else date(desde.year + 1, mes, dia)
    except ValueError:
        return None


def fechas_explicitas(texto: str, publicado: date) -> list[tuple[date, bool]]:
    """Las fechas de un renglón, cada una con si tiene número de día ("jueves 12", "13/11") o es "hoy"/"mañana"."""
    fechas = []
    for numeros, mes in _LISTA_MES.findall(texto):
        for numero in re.findall(r"\d{1,2}", numeros):
            fechas.append((_con_mes(int(numero), MESES[mes], None, publicado), True))
    for dia, mes in _FECHA_MES.findall(texto):
        fechas.append((_con_mes(int(dia), MESES[mes], None, publicado), True))
    for dia, mes, anio in _FECHA_BARRA.findall(texto):
        if 1 <= int(mes) <= 12:
            fechas.append((_con_mes(int(dia), int(mes), int(anio) if anio else None, publicado), True))
    for nombre, numeros in _DIA_NUMERO.findall(texto):
        for numero in re.findall(r"\d{1,2}", numeros):
            fechas.append((_dia_con_numero(int(numero), DIAS[nombre], publicado), True))
    if _HOY.search(texto):
        fechas.append((publicado, False))
    if _MANANA.search(texto):
        fechas.append((publicado + timedelta(days=1), False))
    vistas, resultado = set(), []
    for f, numerada in fechas:
        if f and f not in vistas:
            vistas.add(f)
            resultado.append((f, numerada))
    return resultado


def fechas_de_serie(texto: str, publicado: date) -> list[tuple[date, bool]]:
    fechas = []
    for nombre, mes in _SERIE.findall(texto):
        dia = _con_mes(1, MESES[mes], None, publicado.replace(day=1))
        while dia and dia.month == MESES[mes]:
            if dia.weekday() == DIAS[nombre] and dia >= publicado:
                fechas.append((dia, True))
            dia += timedelta(days=1)
    return fechas


def fechas_por_dia_de_semana(texto: str, publicado: date) -> list[tuple[date, bool]]:
    """'este viernes', 'el jueves': el próximo (o ese mismo día, si el post es de ese día). Necesitan hora."""
    return [(publicado + timedelta(days=(DIAS[nombre] - publicado.weekday()) % 7), False) for nombre in _DIA_SOLO.findall(texto)]


def horas(texto: str) -> list[time]:
    resultado = []
    for grupos in _HORA.findall(texto):
        h1, m1, h2, m2, h3, m3, h4, m4, h5 = grupos
        hora, minutos = (h1, m1) if h1 else (h2, m2) if h2 else (h3, m3) if h3 else (h4, m4) if h4 else (h5, "")
        hora, minutos = int(hora), int(minutos or 0)
        # Un evento a las 5 de la mañana es más probable que sea un error de lectura (o el cierre del bar).
        if minutos < 60 and (hora >= 9 and hora <= 23 or hora <= 3):
            resultado.append(time(hora, minutos))
    return resultado


_SHOW = re.compile(r"(show|comienza|empieza|arranca|inicio|tocan?|sale)\D{0,12}$")
_HASTA = re.compile(r"hasta\D{0,8}$")


def hora_principal(texto: str) -> time | None:
    """La hora de un texto; si hay varias ("puerta 21 hs, show 22 hs"), la del show. "Hasta las 21" no cuenta."""
    validas = [(m, h) for m in _HORA.finditer(texto) for h in horas(m.group(0))
               if not _HASTA.search(texto[max(0, m.start() - 14):m.start()])]
    for m, h in validas:
        if _SHOW.search(texto[max(0, m.start() - 20):m.start()]):
            return h
    if validas:
        return validas[0][1]
    return time(12, 0) if _MEDIODIA.search(texto) else None


def bloques(texto: str, publicado: datetime) -> list[dict]:
    """El post en bloques: cada renglón con fecha abre uno, que sigue hasta el próximo renglón con fecha.

    Así se leen las agendas: "Jueves 12: SPAGUETTI WESTERN" (todo en un renglón) o "Miércoles 04/Noviembre:" con el
    nombre y la hora en los renglones de abajo.
    """
    originales = [r.strip() for r in re.split(r"\n+|(?<=[.!?])\s+", texto or "") if r.strip()]
    sin_tilde = [sin_tildes(r) for r in originales]
    planos = [_RECURRENTE.sub(" ", r) for r in sin_tilde]
    desde = publicado.date()

    def fechas_de(i: int, lector) -> list[tuple[date, bool]]:
        if _NO_ES_EVENTO.search(sin_tilde[i]):
            return []
        # La serie se busca antes de sacar lo recurrente: "todos los martes de noviembre" es un ciclo.
        return fechas_de_serie(sin_tilde[i], desde) + lector(planos[i], desde)

    explicitas = any(fechas_de(i, fechas_explicitas) for i in range(len(planos)))
    lector = fechas_explicitas if explicitas else fechas_por_dia_de_semana
    resultado: list[dict] = []
    for i, (original, plano) in enumerate(zip(originales, planos)):
        fechas = fechas_de(i, lector)
        if fechas:
            resultado.append({"fechas": fechas, "originales": [original], "planos": [plano]})
        elif resultado:
            resultado[-1]["originales"].append(original)
            resultado[-1]["planos"].append(plano)
    return resultado


def _funciones_del_bloque(bloque: dict, unica: time | None, publicado: datetime, desde: datetime) -> list[tuple[datetime, bool]]:
    """Las funciones de un bloque desde `desde` (la hora actual o, para armar el borrador, la del post)."""
    hora = hora_principal(" ".join(bloque["planos"])) or unica
    resultado = []
    for fecha, numerada in bloque["fechas"]:
        if hora is None:
            # Sin hora, solo con el día escrito con número ("jueves 12", "29 de noviembre"), no con "hoy" o "el viernes".
            if numerada and desde.date() <= fecha <= (publicado + HORIZONTE).date():
                resultado.append((datetime.combine(fecha, time(0, 0), tzinfo=desde.tzinfo), True))
            continue
        # "Sábado 14, 00:30" es la madrugada del domingo.
        inicio = datetime.combine(fecha + timedelta(days=1 if hora.hour < 6 else 0), hora, tzinfo=desde.tzinfo)
        if desde - timedelta(hours=3) <= inicio <= publicado + HORIZONTE:
            resultado.append((inicio, False))
    return resultado


def _por_venir(funciones: list[tuple[datetime, bool]], ahora: datetime) -> bool:
    return any(f.date() >= ahora.date() if sin_hora else f >= ahora - timedelta(hours=3) for f, sin_hora in funciones)


def leer_funciones(texto: str, publicado: datetime, ahora: datetime, con_hora: bool = True) -> list[datetime]:
    """Las funciones que anuncia un post (las que tienen hora; con `con_hora=False`, también las de hora a confirmar)."""
    lista = bloques(texto, publicado)
    todas = {h for b in lista for h in [hora_principal(" ".join(b["planos"]))] if h}
    unica = next(iter(todas)) if len(todas) == 1 else None
    return sorted({inicio for b in lista for inicio, sin_hora in _funciones_del_bloque(b, unica, publicado, ahora)
                   if not (con_hora and sin_hora)})


# --- Del post al borrador -----------------------------------------------------------------------------------------

_ADORNOS = re.compile(r"[#@]\w[\w.]*|[^\w\s¡!¿?.,:;\-–—'\"()&/$%+°ºª|]", re.UNICODE)


_DIA_TILDE = r"(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)"
_MES_TEXTO = r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|se?tiembre|octubre|noviembre|diciembre)"
# "Este miércoles en …", "Este viernes 13 de noviembre …": la fecha al principio del título sobra (va aparte).
_FECHA_AL_PRINCIPIO = re.compile(
    rf"^(?:hoy|esta\s+noche|ma[ñn]ana)\b\s*[:,\-–!]*\s*"
    rf"|^(?:(?:este|esta|el|la)\s+(?:pr[oó]ximo\s+)?)?{_DIA_TILDE}\s*(?:\d{{1,2}}(?:\s+de\s+{_MES_TEXTO})?)?\s*(?:en\s+|[:,\-–]\s*)?", re.I)
# "FERIADO + MONKELIS I 2 DE DICIEMBRE EN LA CRETINA": desde la fecha, sobra.
_FECHA_AL_FINAL = re.compile(rf"\s*(?:[|I·\-–—,]\s*)?\b\d{{1,2}}\s+de\s+{_MES_TEXTO}\b.*$", re.I)
# Renglones de propaganda que no sirven de título.
_PROPAGANDA = re.compile(r"inscrib|link (?:en|de) (?:la |nuestra )?bio|entrada (?:gratis|libre)|sorte|reserv|^calendario\b", re.I)
# Encabezados que no son el nombre de nada: el nombre es lo que sigue ("INAUGURACIÓN EXPOSITIVA" y abajo "La sal en las
# paredes"; "NUEVA EDICIÓN! Laboratorio de escritura…"). De una inauguración o un estreno queda dicho en el título.
_ENCABEZADO = re.compile(
    r"^(?:(inauguraci[oó]n|estreno)(?:\s+expositiva|\s+de\s+(?:la\s+)?(?:muestra|exposici[oó]n))?"
    r"|nueva\s+edici[oó]n|nueva\s+fecha|se\s+viene|atenci[oó]n|importante|[uú]ltimos?\s+(?:lugares|cupos))\s*(?:[!:.]+\s*|$)", re.I)


def _limpiar(renglon: str) -> str:
    return re.sub(r"\s+", " ", _ADORNOS.sub(" ", renglon)).strip(" -–—:.,!¡")


def titulo_de(texto: str, cuenta: str) -> str:
    """El primer renglón con algo de texto, sin emojis, hashtags, menciones, fecha ni propaganda.

    Si al renglón se le sacó la fecha y abajo viene un nombre corto, se suma: "Noches De Ensayos Abiertos · Lali
    Gaspari" (de "Este miércoles en Noches De Ensayos Abiertos" y "Lali Gaspari").
    """
    renglones = [_limpiar(r) for r in (texto or "").splitlines()]
    renglones = [r for r in renglones if len(re.sub(r"\W", "", r)) >= 4]
    prefijo = None
    for i, limpio in enumerate(renglones):
        encabezado = _ENCABEZADO.match(limpio)
        if encabezado:
            prefijo = prefijo or (encabezado.group(1) or "").capitalize() or None
            limpio = limpio[encabezado.end():].strip(" -–—:.,!¡")
            if len(re.sub(r"\W", "", limpio)) < 4:
                continue
        if _PROPAGANDA.search(limpio) or re.fullmatch(r"[a-z0-9._]{4,}", limpio):
            continue
        sin_principio = _FECHA_AL_PRINCIPIO.sub("", limpio)
        sin_fecha = _FECHA_AL_FINAL.sub("", sin_principio).strip(" -–—:.,")
        sin_fecha = re.sub(r"\s+(?:este|esta|el|la|del|de|en|por)$", "", sin_fecha, flags=re.I)  # "…por eso este 24 de dic"
        # La hora también va aparte: "SPAGUETTI WESTERN 22 hs" es "SPAGUETTI WESTERN".
        sin_fecha = re.sub(r"\s*[-–·,/|]?\s*\b\d{1,2}(?:[:.]\d{2})?\s*(?:h|hs|hrs|horas)\b.*$", "", sin_fecha, flags=re.I).strip(" -–—:.,")
        if len(re.sub(r"\W", "", sin_fecha)) < 4:
            continue
        if sin_principio != limpio and i + 1 < len(renglones):
            abajo = renglones[i + 1]
            if len(abajo) <= 40 and len(abajo.split()) <= 5 and abajo[:1].isupper() and not _PROPAGANDA.search(abajo) \
                    and not re.search(r"\d", abajo) and not abajo.endswith(".") \
                    and sin_tildes(abajo) not in sin_tildes(sin_fecha):
                sin_fecha = f"{sin_fecha} · {abajo}"
        # "MAMBO | De Miguel Morillo": el nombre es lo de antes de la barra.
        partes = re.split(r"\s\|\s", sin_fecha)
        if len(partes) > 1 and len(re.sub(r"\W", "", partes[0])) >= 4:
            sin_fecha = partes[0]
        limpio = sin_fecha[0].upper() + sin_fecha[1:]
        if len(limpio) > 60:
            # "Laboratorio de escritura a cargo de terepuppo, para explorar…": el nombre es lo de antes.
            corto = re.split(r"\s+a\s+cargo\s+de\b", limpio)[0]
            limpio = corto if len(re.sub(r"\W", "", corto)) >= 4 else limpio
        if len(limpio) > 90:
            limpio = re.split(r"(?<=[.!?])\s", limpio)[0]
        if prefijo and sin_tildes(prefijo) not in sin_tildes(limpio):
            limpio = f"{prefijo} de {limpio}"
        return limpio if len(limpio) <= 90 else limpio[:87].rsplit(" ", 1)[0] + "…"
    return f"En {cuenta}"  # con_el_bar no le vuelve a sumar el nombre


def precio_del_texto(texto: str):
    plano = texto or ""
    if re.search(r"gratis|entrada libre|sin costo|gratuit", plano, re.I):
        return precio_de("gratis")
    montos = re.findall(r"\$\s*\d[\d.]*", plano)
    return precio_de(" - ".join(montos)) if montos else None


_PIN = re.compile(r"📍\s*([^\n]+)")
_NO_ES_LUGAR = re.compile(r"modalidad|virtual|online|zoom|a confirmar|por definir|\blink\b", re.I)


def lugar_del_texto(texto: str) -> tuple[str | None, str | None]:
    """El lugar que dice el post con 📍: "📍La Cretina, Soriano 1236" o "📍 Museo Oceanográfico". (nombre, dirección)."""
    encontrado = _PIN.search(texto or "")
    if not encontrado or _NO_ES_LUGAR.search(encontrado.group(1)):
        return None, None  # "📍 Modalidad presencial o virtual" no dice dónde
    # Hasta el primer emoji: "📍 MBC Ombú ⚠️ Cupos limitados" es solo "MBC Ombú".
    renglon = re.split(r"[^\w\s,.'\-–&/°ºª()]", encontrado.group(1))[0].strip(" -–,.")
    partes = [p.strip() for p in re.split(r",|\s[-–]\s", renglon) if p.strip()]
    if not partes:
        return None, None
    if len(partes) == 1 and re.search(r"\d", partes[0]):
        return None, partes[0]  # "📍 Soriano 1236": solo la dirección
    direccion = next((p for p in partes[1:] if re.search(r"\d", p)), None)
    return partes[0], direccion


_SEPARADOR = re.compile(r"\s*[:–—|]\s*|\s-\s")
_SIN_NOMBRE = re.compile(r"a confirmar|cerrado|^\W*$", re.I)
_DATOS_PRACTICOS = re.compile(r"entradas|venta|reserv|cubierto|precio|\$|whatsapp|tel[eé]fono", re.I)


def titulo_del_bloque(originales: list[str]) -> str | None:
    """El nombre de lo que pasa ese día: lo que sigue a "Jueves 12:" o, si no hay nada, el renglón de abajo."""
    primero = _SEPARADOR.split(originales[0], maxsplit=1)
    candidatos = ([primero[1]] if len(primero) > 1 else []) + originales[1:2]
    for candidato in candidatos:
        # Ni el lugar (📍) ni la venta de entradas o el precio son el nombre de lo que pasa ese día.
        if "📍" in candidato or _DATOS_PRACTICOS.search(candidato):
            continue
        limpio = re.sub(r"\s+", " ", _ADORNOS.sub(" ", candidato)).strip()
        # Hasta el primer " - ", paréntesis, punto u hora: "OPEN MIC NIGHT - 4ta temporada" es "OPEN MIC NIGHT".
        limpio = re.split(r"\s[-–—|]\s|\(|\.\s|\.$|\b\d{1,2}([:.]\d{2})?\s*(h|hs|hrs|horas)\b", limpio)[0].strip(" -–—:.,")
        if len(re.sub(r"\W", "", limpio)) >= 3 and not _SIN_NOMBRE.search(limpio) and not _no_es_titulo(limpio):
            return limpio if len(limpio) <= 90 else limpio[:87].rsplit(" ", 1)[0] + "…"
    return None


def _no_es_titulo(texto: str) -> bool:
    """Un pedazo de fecha ("lunes 30") o un usuario de Instagram suelto ("alejandropersichetti") no son un título."""
    sin_fecha = _FECHA_AL_PRINCIPIO.sub("", texto).strip(" -–—:.,|")
    # Tampoco un encabezado ("Diciembre:", "Funciones:") ni algo hecho solo de fechas ("Miércoles 11 y 18 | Lunes 30").
    resto = re.sub(rf"{_DIA}s?|{_MES}|funciones|fechas|horarios|agenda|\d+|\by\b|\bde\b|\W", "", sin_tildes(texto))
    return len(re.sub(r"\W", "", sin_fecha)) < 3 or bool(re.fullmatch(r"[a-z0-9._]{4,}", texto)) or len(resto) < 3


def nombre_corto(nombre: str) -> str:
    """Cómo se nombra al bar en el título: sin emojis, hasta el primer "|" o " - ", y sin todo en mayúsculas.

    "MBC | MONTEVIDEO BEER COMPANY" → "MBC"; "Brecha Bar y Café 🏳️‍🌈" → "Brecha Bar y Café"; "INMIGRANTES" → "Inmigrantes".
    """
    limpio = _limpiar(re.split(r"\s*[|·•]\s*|\s[-–—]\s", nombre)[0])
    if limpio.isupper() and len(limpio) > 4:
        limpio = limpio.title()
    return limpio or nombre


def con_el_bar(titulo: str, bar: str) -> str:
    """"The Shannon: SPAGUETTI WESTERN". Si el título ya nombra al bar, queda como está."""
    if sin_tildes(bar) in sin_tildes(titulo):
        return titulo
    return f"{bar}: {titulo}"


def _clave(texto: str) -> str:
    return re.sub(r"[^a-z0-9]", "", sin_tildes(texto))


def _con_lugar_fijo(cuenta: dict) -> bool:
    return bool(cuenta.get("direccion") or cuenta.get("lat"))


def cuenta_del_lugar(nombre: str) -> dict | None:
    """La cuenta de la lista que es ese lugar, si se sabe dónde queda: el 📍 "MuMi" es "MuMI - Muralla Abierta"."""
    buscado = _clave(nombre)
    if len(buscado) < 4:
        return None
    for c in cuentas():
        nombres = {c["usuario"], c.get("corto") or "", c.get("nombre") or "", re.split(r"\s[-–]\s", c.get("nombre") or "")[0]}
        if _con_lugar_fijo(c) and buscado in {_clave(n) for n in nombres if n}:
            return c
    return None


def cuenta_mencionada(texto: str, propia: str) -> dict | None:
    """El primer lugar de la lista que nombra el post por su usuario ("Plaza ex Terminal Goes centroculturalterminalgoes")."""
    for c in cuentas():
        if c["usuario"] != propia and _con_lugar_fijo(c) and re.search(rf"(?<![\w.]){re.escape(c['usuario'])}(?![\w])", texto):
            return c
    return None


def _un_borrador(cuenta: dict, perfil: dict, post: dict, publicado: datetime, funciones: list[tuple[datetime, bool]],
                 titulo: str, extracto: str) -> dict:
    texto = post.get("caption") or ""
    # Una función por día: si el texto da dos horas para el mismo día ("a las 20" y más abajo "19:00 h"), la primera;
    # y si un día aparece con y sin hora, con hora.
    por_dia: dict[date, tuple[datetime, bool]] = {}
    for inicio, sin_hora in funciones:  # en el orden del texto
        dia = _dia(inicio)
        if dia not in por_dia or (por_dia[dia][1] and not sin_hora):
            por_dia[dia] = (inicio, sin_hora)
    lista = sorted(por_dia.values())
    imagen = post.get("media_url") if post.get("media_type") in ("IMAGE", "CAROUSEL_ALBUM") else None
    del_bar = cuenta.get("nombre") or perfil.get("name") or cuenta["usuario"]
    nombre, direccion = lugar_del_texto(texto)
    # Si el 📍 nombra al mismo bar (o solo da la dirección), el lugar es el bar; si nombra otro lugar, ese.
    otro_lugar = nombre and sin_tildes(nombre) not in sin_tildes(del_bar) and sin_tildes(del_bar) not in sin_tildes(nombre)
    # Si ese otro lugar está en la lista, con su dirección. Una cuenta sin lugar fijo (una feria, un festival) que no
    # dice dónde con 📍 puede nombrar al lugar por su usuario.
    conocido = cuenta_del_lugar(nombre) if otro_lugar else None
    if not nombre and cuenta.get("itinerante"):
        conocido = cuenta_mencionada(texto, cuenta["usuario"])
    if conocido and conocido["usuario"] != cuenta["usuario"]:
        nombre, direccion, otro_lugar = conocido.get("nombre") or nombre or conocido["usuario"], conocido.get("direccion"), True
    else:
        conocido = None
    return {
        # Un borrador por cuenta y día: el mismo evento anunciado en varios posts (o en la agenda del mes y en la de
        # la semana) queda uno solo.
        "id": f"{cuenta['usuario']}-{_dia(lista[0][0]):%Y%m%d}",
        "usuario": cuenta["usuario"],
        "lugar": nombre if otro_lugar else del_bar,
        "direccion": direccion if otro_lugar else cuenta.get("direccion") or direccion,
        "barrio": (conocido or {}).get("barrio") if otro_lugar else cuenta.get("barrio"),
        # Para los bares que solo dan una esquina ("Durazno y Jackson"), que el buscador de direcciones no encuentra.
        "lat": (conocido or {}).get("lat") if otro_lugar else cuenta.get("lat"),
        "lon": (conocido or {}).get("lon") if otro_lugar else cuenta.get("lon"),
        "lugar_del_pin": bool(otro_lugar),
        # Lo que pasa en el bar lleva la etiqueta "Bares" en el sitio; no si es en otro lugar, ni si la cuenta no es de
        # un bar (una sala o un mercado: `bar = false` en la lista).
        "bar": conocido.get("bar", True) if conocido else not otro_lugar and cuenta.get("bar", True),
        "titulo": con_el_bar(titulo, cuenta.get("corto") or nombre_corto(del_bar)),
        "texto": texto,
        "extracto": extracto,
        "funciones": [{"inicio": inicio.isoformat(), "sin_hora": sin_hora} for inicio, sin_hora in lista],
        "url": post["permalink"],
        "posts": [post["permalink"]],
        "imagen": imagen,
        "publicado": publicado.isoformat(),
    }


def _dia(inicio: datetime) -> date:
    """El día de la función: lo de la madrugada (antes de las 6) cuenta para la noche anterior."""
    return (inicio - timedelta(hours=6)).date() if inicio.hour < 6 and (inicio.hour or inicio.minute) else inicio.date()


def borradores_del_post(post: dict, cuenta: dict, perfil: dict, ahora: datetime) -> list[dict]:
    """Lo que anuncia un post, todavía por venir: un borrador, o uno por día si es una agenda."""
    texto = post.get("caption") or ""
    publicado = datetime.fromisoformat(post["timestamp"].replace("+0000", "+00:00")).astimezone(ahora.tzinfo)
    if ahora - publicado > ANTIGUEDAD_MAXIMA or _CONVOCATORIA.search(sin_tildes(texto[:300])):
        return []
    lista = bloques(texto, publicado)
    todas = {h for b in lista for h in [hora_principal(" ".join(b["planos"]))] if h}
    unica = next(iter(todas)) if len(todas) == 1 else None
    del_bar = cuenta.get("nombre") or perfil.get("name") or cuenta["usuario"]
    # Una agenda: varios días, cada uno con su nombre ("Jueves 12: SPAGUETTI WESTERN", "Viernes 13: PROYECTO OLDIES").
    dias = {f for b in lista for f, _ in b["fechas"]}
    titulos = [titulo_del_bloque(b["originales"]) for b in lista]
    # Las funciones se cuentan desde el post, no desde hoy: así el borrador conserva su identificador (el de su primer
    # día) aunque ese día ya haya pasado. Las que ya pasaron no se publican (ver evento_de).
    if len(dias) >= 2 and sum(1 for t in titulos if t) >= 2:
        resultado = []
        for b, titulo in zip(lista, titulos):
            funciones = _funciones_del_bloque(b, None, publicado, publicado)
            if titulo and _por_venir(funciones, ahora):
                resultado.append(_un_borrador(cuenta, perfil, post, publicado, funciones, titulo, " ".join(b["originales"])))
        return resultado
    funciones = [f for b in lista for f in _funciones_del_bloque(b, unica, publicado, publicado)]
    if not _por_venir(funciones, ahora):
        return []
    return [_un_borrador(cuenta, perfil, post, publicado, funciones, titulo_de(texto, del_bar), texto)]


def juntar(previo: dict, nuevo: dict) -> dict:
    """El mismo evento en dos posts: vale el más reciente (lo último que dijeron), con los enlaces de los dos.

    El título es el más corto de los dos, que suele ser el nombre del evento ("TABAREK & LA KABARET" y no "Tenemos el
    honor de recibir…"). Si solo uno dice dónde es (con 📍) o a qué hora, eso sale de ese.
    """
    base, otro = (nuevo, previo) if nuevo["publicado"] > previo["publicado"] else (previo, nuevo)
    junto = {**base, "posts": sorted(set(base["posts"]) | set(otro["posts"])), "imagen": base["imagen"] or otro["imagen"]}
    if len(otro["titulo"]) >= 8 and len(otro["titulo"]) < len(base["titulo"]):
        junto["titulo"] = otro["titulo"]
    if otro.get("lugar_del_pin") and not base.get("lugar_del_pin"):
        junto.update({k: otro.get(k) for k in ("lugar", "direccion", "barrio", "lat", "lon", "lugar_del_pin", "bar")})
    # Los días de los dos (un post con el ciclo del mes y otro con un martes); para cada día, con hora si alguno la da.
    por_dia: dict[date, dict] = {}
    for f in base["funciones"] + otro["funciones"]:
        dia = _dia(datetime.fromisoformat(f["inicio"]))
        if dia not in por_dia or (por_dia[dia]["sin_hora"] and not f["sin_hora"]):
            por_dia[dia] = f
    junto["funciones"] = [por_dia[d] for d in sorted(por_dia)]
    return junto


def juntar_parecidos(borradores: dict[str, dict]) -> dict[str, dict]:
    """Junta los borradores del mismo bar que comparten algún día y tienen un título parecido.

    Pasa con una obra en temporada: el post del estreno ("21 de octubre…") y el de "Esta noche: MAMBO" arrancan en días
    distintos y tendrían dos identificadores. Queda el del primer día (el que ya se avisó, casi siempre).
    """
    lista = sorted(borradores.values(), key=lambda b: (b["funciones"][0]["inicio"], b["id"]))
    resultado: list[dict] = []
    for b in lista:
        dias = {_dia(f.inicio) for f in _funciones(b)}
        for i, otro in enumerate(resultado):
            if otro["usuario"] == b["usuario"] and dias & {_dia(f.inicio) for f in _funciones(otro)} \
                    and fuzz.token_set_ratio(sin_tildes(otro["titulo"]), sin_tildes(b["titulo"])) >= 75:
                resultado[i] = {**juntar(otro, b), "id": otro["id"]}
                break
        else:
            resultado.append(b)
    return {b["id"]: b for b in resultado}


def _funciones(b: dict) -> list[Funcion]:
    return [Funcion(inicio=datetime.fromisoformat(f["inicio"]), sin_hora=f["sin_hora"]) for f in b["funciones"]]


def evento_de(b: dict, ahora: datetime) -> EventoCrudo | None:
    funciones = [f for f in _funciones(b) if (f.inicio.date() >= ahora.date() if f.sin_hora else f.inicio >= ahora - timedelta(hours=3))]
    if not funciones:
        return None
    titulo = b.get("titulo_aprobado") or b["titulo"]
    texto = b.get("extracto") or b["texto"]
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=b["id"],
        url=b["url"],
        titulo=titulo,
        categoria=clasificar(titulo, texto, por_defecto="otros"),
        descripcion_corta=recortar(re.sub(r"\s+", " ", _ADORNOS.sub(" ", texto)).strip()),
        lugar=LugarCrudo(nombre=b["lugar"], direccion=b.get("direccion"), barrio=b.get("barrio"), lat=b.get("lat"), lon=b.get("lon")),
        funciones=funciones,
        precio=precio_del_texto(texto),
        entradas=[Entrada(url=b["url"], via="instagram")],
        etiquetas=["bar"] if b.get("bar") else [],
    )


# --- Las aprobaciones: casillas en los avisos de GitHub -----------------------------------------------------------

_RENGLON = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.*?)<!--\s*ig:([\w.-]+)\s*-->", re.M)


def renglon_del_borrador(b: dict) -> str:
    dias = ", ".join(_cuando(f) for f in _funciones(b))
    titulo = b["titulo"].replace("*", "")
    extracto = recortar(re.sub(r"\s+", " ", b.get("extracto") or b["texto"]), 220)
    # El usuario de Instagram va entre comillas de código: con una @ suelta, GitHub avisaría a alguien con ese nombre.
    via = f" (vía `{b['usuario']}`)" if b.get("usuario") else ""
    mas = len(b.get("posts", [])) - 1
    post = f"[ver el post]({b['url']})" + (f" (y {mas} {'post' if mas == 1 else 'posts'} más sobre lo mismo)" if mas > 0 else "")
    return (f"- [ ] **{titulo}** · {b['lugar']}{via} · {dias} · {post} <!-- ig:{b['id']} -->\n"
            f"  > {extracto}")


def _cuando(funcion: Funcion) -> str:
    dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
    inicio = funcion.inicio
    return f"{dias[inicio.weekday()]} {inicio:%d/%m} " + ("(la hora está en el post)" if funcion.sin_hora else f"{inicio:%H:%M}")


def leer_casillas(cuerpos: list[str]) -> tuple[dict[str, str | None], set[str]]:
    """De los avisos: los borradores tildados (con el título, si se cambió) y todos los que ya se avisaron."""
    aprobados, avisados = {}, set()
    for cuerpo in cuerpos:
        for marca, resto, id_ in _RENGLON.findall(cuerpo or ""):
            avisados.add(id_)
            if marca.lower() == "x":
                titulo = re.search(r"\*\*(.+?)\*\*", resto)
                aprobados[id_] = titulo.group(1).strip() if titulo else None
    return aprobados, avisados


def avisos_en_github() -> list[dict] | None:
    """Los avisos de borradores (abiertos y cerrados). None si no hay cómo preguntarle a GitHub."""
    if not os.environ.get("GH_TOKEN"):
        return None
    try:
        salida = subprocess.run(
            ["gh", "issue", "list", "--label", ETIQUETA, "--state", "all", "--limit", "200", "--json", "number,body,state"],
            check=True, capture_output=True, text=True,
        ).stdout
        return json.loads(salida or "[]")
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        log.warning("%s: no se pudieron leer los avisos de GitHub (%s)", NOMBRE, error)
        return None


# --- La corrida ---------------------------------------------------------------------------------------------------


def cuentas(ruta: Path | None = None) -> list[dict]:
    return tomllib.loads((ruta or CONFIG).read_text(encoding="utf-8")).get("bar", [])


def cargar_borradores() -> dict[str, dict]:
    if not BORRADORES.exists():
        return {}
    # Solo los del formato actual (cada función con su "sin_hora"); los de una versión anterior se vuelven a armar.
    return {b["id"]: b for b in json.loads(BORRADORES.read_text(encoding="utf-8"))
            if all(isinstance(f, dict) for f in b.get("funciones", []))}


def guardar_borradores(borradores: dict[str, dict]) -> None:
    BORRADORES.parent.mkdir(parents=True, exist_ok=True)
    lista = sorted(borradores.values(), key=lambda b: (b["funciones"][0]["inicio"], b["id"]))
    BORRADORES.write_text(json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8")


def vigente(b: dict, ahora: datetime) -> bool:
    ultima = _funciones(b)[-1]
    return ultima.inicio.date() >= ahora.date() if ultima.sin_hora else ultima.inicio >= ahora - timedelta(hours=3)


def poner_afiche(http: httpx.Client, b: dict, evento: EventoCrudo) -> str | None:
    """Baja la imagen del post (con un cliente sin la clave: el servidor de imágenes no la necesita)."""
    archivo = DIR_AFICHES / f"{hashlib.sha1(b['id'].encode()).hexdigest()[:12]}.jpg"
    if not archivo.exists():
        if not b.get("imagen"):
            return None
        try:
            if not guardar_afiche(http.get(b["imagen"]).content, archivo):
                return f"{b['titulo']}: la imagen del post no se pudo usar"
        except httpx.HTTPError as error:
            return f"{b['titulo']}: no se pudo bajar la imagen del post ({type(error).__name__})"
    evento.imagen_url = f"{URL_SITIO}afiches/instagram/{archivo.name}"
    return None


def cuenta_de_la_gestoria(http: httpx.Client, token: str) -> str:
    """El número de la cuenta de Instagram de La Gestoría, desde la que se consulta.
    """
    yo = http.get(f"{GRAPH}/me", params={"fields": "instagram_business_account"}).json()
    if ig_id := (yo.get("instagram_business_account") or {}).get("id"):
        return ig_id
    datos = http.get(f"{GRAPH}/debug_token", params={"input_token": token}).json().get("data") or {}
    for permiso in datos.get("granular_scopes") or []:
        if permiso.get("scope") == "instagram_basic" and permiso.get("target_ids"):
            return permiso["target_ids"][0]
    raise RuntimeError(f"la clave no da la cuenta de Instagram de La Gestoría: {yo.get('error', yo)}")


def scrapear(cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    token = os.environ.get("INSTAGRAM_TOKEN", "").strip()
    if not token:
        # Falla a propósito: así queda el último resultado bueno (no se borran los eventos ya aprobados).
        raise RuntimeError("falta la clave INSTAGRAM_TOKEN")
    errores: list[str] = []
    borradores = cargar_borradores()
    with (httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT, "Authorization": f"Bearer {token}"},
                       transport=TRANSPORTE) as http,
          httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True, transport=TRANSPORTE) as imagenes):
        ig_id = cuenta_de_la_gestoria(http, token)
        campos_post = "id,caption,media_type,media_url,permalink,timestamp"
        esta_corrida: dict[str, dict] = {}
        estado: dict[str, str] = {}
        leidos: list[dict] = []
        for cuenta in cuentas():
            usuario = cuenta["usuario"]
            campos = f"business_discovery.username({usuario}){{name,media.limit({POSTS_POR_CUENTA}){{{campos_post}}}}}"
            try:
                datos = http.get(f"{GRAPH}/{ig_id}", params={"fields": campos}).json()
            except (httpx.HTTPError, ValueError) as error:
                errores.append(f"@{usuario}: {type(error).__name__}")
                continue
            if "error" in datos:
                # Una cuenta personal (no profesional) o que cambió de nombre no se puede leer: se avisa en el
                # registro, pero no cuenta como falla de la fuente.
                log.warning("%s: @%s no se pudo leer: %s", NOMBRE, usuario, datos["error"].get("message"))
                estado[usuario] = f"no se pudo leer: {datos['error'].get('message')}"
                continue
            perfil = datos.get("business_discovery") or {}
            posts = (perfil.get("media") or {}).get("data") or []
            leidos += [{"usuario": usuario, "timestamp": p.get("timestamp"), "url": p.get("permalink"),
                        "caption": p.get("caption")} for p in posts]
            antes = len(esta_corrida)
            for post in posts:
                try:
                    nuevos = borradores_del_post(post, cuenta, perfil, ahora)
                except (KeyError, ValueError) as error:
                    errores.append(f"{usuario}: post raro ({type(error).__name__})")
                    continue
                for nuevo in nuevos:
                    previo = esta_corrida.get(nuevo["id"])
                    esta_corrida[nuevo["id"]] = juntar(previo, nuevo) if previo else nuevo
            estado[usuario] = f"leída: {len(posts)} posts, {len(esta_corrida) - antes} borradores"

        # Lo que ya no sale de los posts (por ejemplo, porque cambiaron las reglas) se va, salvo que esté aprobado:
        # un evento anunciado con mucha anticipación puede quedar fuera de los últimos posts y tiene que seguir.
        anteriores = borradores
        borradores = {i: b for i, b in anteriores.items() if b.get("aprobado") and i not in esta_corrida}
        esta_corrida = juntar_parecidos(esta_corrida)
        for id_, nuevo in esta_corrida.items():
            anterior = anteriores.get(id_, {})
            # Lo que se decidió en GitHub se conserva; lo demás se actualiza (la imagen vence).
            borradores[id_] = {**nuevo, **{k: anterior[k] for k in ("aprobado", "titulo_aprobado") if k in anterior}}
        ESTADO.parent.mkdir(parents=True, exist_ok=True)
        if os.environ.get("IG_GUARDAR_POSTS"):
            POSTS_LEIDOS.write_text(json.dumps(leidos, ensure_ascii=False, indent=1), encoding="utf-8")
        ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
        sin_leer = [f"@{u}" for u, e in estado.items() if e.startswith("no se pudo")]
        log.info("%s: %s de %s cuentas leídas%s", NOMBRE, len(estado) - len(sin_leer), len(estado),
                 f"; sin poder leer: {', '.join(sin_leer)}" if sin_leer else "")

        borradores = {i: b for i, b in borradores.items() if vigente(b, ahora)}
        avisos = avisos_en_github()
        if avisos is not None:
            aprobados, _ = leer_casillas([a.get("body", "") for a in avisos])
            for id_, b in borradores.items():
                b["aprobado"] = id_ in aprobados
                b["titulo_aprobado"] = aprobados.get(id_)
        guardar_borradores(borradores)

        eventos = []
        for b in borradores.values():
            if not b.get("aprobado"):
                continue
            evento = evento_de(b, ahora)
            if evento:
                if problema := poner_afiche(imagenes, b, evento):
                    errores.append(problema)
                eventos.append(evento)

    # Las imágenes de lo que ya no se publica se borran.
    usadas = {e.imagen_url.rsplit("/", 1)[-1] for e in eventos if e.imagen_url}
    for archivo in DIR_AFICHES.glob("*.jpg"):
        if archivo.name not in usadas:
            archivo.unlink()
    log.info("%s: %s borradores vigentes, %s aprobados", NOMBRE, len(borradores), len(eventos))
    return eventos, errores


# --- El aviso diario ----------------------------------------------------------------------------------------------

INTRO = (
    "Posts de bares y salas que parecen anunciar algo. **Tildá los que querés publicar**: entran al sitio en la "
    "próxima actualización (8:17, 12:17 o 18:17; GitHub a veces las atrasa).\n\n"
    "- Para cambiar el título, editá el aviso (los tres puntos ⋯ → Edit) y cambiá lo que va entre `**`.\n"
    "- Si te arrepentís, sacá el tilde y se va en la actualización siguiente.\n"
    "- Lo que no tildes no se publica. Este aviso se cierra solo cuando pasan todas las fechas.\n"
)


def avisar(en_github: bool = False, ahora: datetime | None = None) -> list[dict]:
    """Abre un aviso con los borradores que todavía no se avisaron y cierra los avisos que ya pasaron."""
    ahora = ahora or datetime.now(MONTEVIDEO)
    vigentes = {i: b for i, b in cargar_borradores().items() if vigente(b, ahora)}
    avisos = avisos_en_github() if en_github else None
    _, avisados = leer_casillas([a.get("body", "") for a in avisos or []])
    nuevos = [b for i, b in vigentes.items() if i not in avisados]
    for b in nuevos:
        log.info("borrador de Instagram: %s (@%s)", b["titulo"], b["usuario"])
    if not en_github or avisos is None:
        return nuevos
    repo = os.environ.get("GH_REPO", "")
    if nuevos:
        subprocess.run(["gh", "label", "create", ETIQUETA, "--color", "E4A94A", "--force",
                        "--description", "Posts de Instagram para aprobar"], check=False, capture_output=True)
        cuerpo = INTRO + "\n" + "\n".join(renglon_del_borrador(b) for b in nuevos) + "\n"
        titulo = f"Instagram: {len(nuevos)} {'borrador nuevo' if len(nuevos) == 1 else 'borradores nuevos'} ({ahora:%d/%m %H:%M})"
        comando = ["gh", "issue", "create", "--title", titulo, "--body", cuerpo, "--label", ETIQUETA]
        if "/" in repo:
            comando += ["--assignee", repo.split("/")[0]]  # asignado a la dueña del repo: le llega el correo
        subprocess.run(comando, check=True)
    # Un aviso abierto cuyos borradores ya pasaron (o se fueron) se cierra.
    for aviso in avisos:
        if aviso.get("state") != "OPEN":
            continue
        _, ids = leer_casillas([aviso.get("body", "")])
        if ids and not ids & set(vigentes):
            subprocess.run(["gh", "issue", "close", str(aviso["number"]), "--comment", "Ya pasaron todas las fechas."],
                           check=False)
    return nuevos
