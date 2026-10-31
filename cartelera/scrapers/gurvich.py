"""Museo Gurvich: exposiciones con su período y la agenda de actividades (WordPress, HTML del servidor).

La página de exposiciones trae cada una con "Del 05 nov 2026 Al 15 jun 2027"; la portada, la agenda
de actividades con su fecha ("29 oct 2026 | Actividad").
"""

import html
import re
from datetime import date, datetime, time

from cartelera.categorias import clasificar, esta_cancelado
from cartelera.extraer import recortar, texto_plano
from cartelera.geo import sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo
from cartelera.scrapers.muestras import funciones_de_muestra, mes_de

NOMBRE = "gurvich"
BASE = "https://museogurvich.org"
LUGAR = LugarCrudo(nombre="Museo Gurvich", direccion="Sarandí 524", lat=-34.90748, lon=-56.20430)
_FECHA = re.compile(r"(\d{1,2}) ([a-z]+)\.? (\d{4})")
_EXPOSICION = re.compile(
    r'<a href="(https://museogurvich\.org/exposiciones/[^"]+)">\s*<figure[^>]*>\s*(?:<img src="([^"]+)")?.*?<h3>(.*?)</h3>.*?<h6>(.*?)</h6>', re.S,
)
_ACTIVIDAD = re.compile(
    r'<a data-agenda="[^"]*" href="(https://museogurvich\.org/actividad/[^"]+)"[^>]*>(.*?)</a>', re.S,
)


def fechas(texto: str) -> list[date]:
    encontradas = []
    for dia, mes, anio in _FECHA.findall(sin_tildes(texto)):
        if numero := mes_de(mes):
            encontradas.append(date(int(anio), numero, int(dia)))
    return encontradas


def exposiciones(pagina: str, ahora: datetime) -> list[EventoCrudo]:
    eventos = []
    for url, imagen, titulo, periodo in _EXPOSICION.findall(pagina):
        titulo, rango = texto_plano(titulo), fechas(texto_plano(periodo))
        if not titulo or not rango or esta_cancelado(titulo) or rango[-1] < ahora.date():
            continue
        funciones = funciones_de_muestra(rango[0], rango[-1], ahora)
        if funciones and url not in {e.url for e in eventos}:
            eventos.append(EventoCrudo(
                fuente=NOMBRE, id_externo=url.rstrip("/").rsplit("/", 1)[-1], url=url, titulo=titulo,
                categoria="exposicion", categoria_segura=True, lugar=LUGAR, funciones=funciones,
                entradas=[Entrada(url=url, via=NOMBRE)], imagen_url=imagen or None, productor="Museo Gurvich",
                muestra=True, hasta=rango[-1],
            ))
    return eventos


def actividades(pagina: str, ahora: datetime) -> list[EventoCrudo]:
    eventos = []
    for url, cuerpo in _ACTIVIDAD.findall(pagina):
        tipo = re.search(r'cyg--cate">([^<]+)<', cuerpo)
        if tipo and "exposic" in sin_tildes(tipo.group(1)):
            continue  # las exposiciones salen de su propia página, con el período completo
        titulo = re.search(r'<h3 title="([^"]+)"', cuerpo)
        cuando = re.search(r'cyg--fecha">([^<]+)<', cuerpo)
        dias = fechas(cuando.group(1)) if cuando else []
        if not titulo or not dias or dias[0] < ahora.date():
            continue
        # "Mes de la música | 29 de octubre": la fecha ya está aparte.
        nombre = re.sub(r"\s*\|\s*\d{1,2} de [a-záéíóú]+\s*$", "", html.unescape(titulo.group(1))).strip()
        imagen = re.search(r"background-image: url\(&quot;([^&]+)&quot;\)", cuerpo)
        resumen = re.search(r'wcs-class__excerpt">(.*?)</div>', cuerpo, re.S)
        descripcion = texto_plano(resumen.group(1)) if resumen else ""
        eventos.append(EventoCrudo(
            fuente=NOMBRE, id_externo=url.rstrip("/").rsplit("/", 1)[-1], url=url, titulo=nombre,
            categoria=clasificar(nombre, descripcion, por_defecto="charla"), descripcion_corta=recortar(descripcion),
            lugar=LUGAR, funciones=[Funcion(inicio=datetime.combine(dias[0], time(0, 0), tzinfo=ahora.tzinfo), sin_hora=True)],
            entradas=[Entrada(url=url, via=NOMBRE)], imagen_url=imagen.group(1) if imagen else None, productor="Museo Gurvich",
        ))
    return eventos


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos = exposiciones(cliente.texto(f"{BASE}/exposiciones/"), ahora) + actividades(cliente.texto(f"{BASE}/"), ahora)
    return eventos, []
