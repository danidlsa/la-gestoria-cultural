"""Calendario de actividades del MEC (gub.uy): solo lo que pasa en museos de Montevideo.

El calendario del Ministerio junta todo lo suyo (el Sodre, giras por el interior, congresos); de ahí se
toman las actividades en museos (visitas comentadas, inauguraciones, talleres), que muchos museos
nacionales no publican en otro lado. Cada ítem del listado trae la fecha, la hora, el lugar y el título.
"""

import html
import re
from datetime import date, datetime, time

from cartelera.categorias import clasificar, esta_cancelado
from cartelera.extraer import texto_plano
from cartelera.geo import menciona_otra_ciudad, sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo
from cartelera.scrapers.muestras import mes_de

NOMBRE = "mec_museos"
BASE = "https://www.gub.uy"
CALENDARIO = f"{BASE}/ministerio-educacion-cultura/comunicacion/calendario-actividades"
MAX_PAGINAS = 4
_ITEM = re.compile(r'<article about="([^"]+)">(.*?)</article>', re.S)
_RUBROS = [
    ("tour", re.compile(r"\b(visitas? (guiadas?|comentadas?|mediadas?)|recorrido)")),
    ("taller", re.compile(r"\b(taller|curso|clase)\w*")),
]


def leer_listado(pagina: str) -> list[dict]:
    items = []
    for ruta, cuerpo in _ITEM.findall(pagina):
        dato = lambda clase: (re.search(rf'class="{clase}">(.*?)</div>', cuerpo, re.S) or [None, ""])[1]  # noqa: E731
        titulo = re.search(r'Event-title">\s*<a[^>]*>(.*?)</a>', cuerpo, re.S)
        items.append({
            "ruta": ruta,
            "titulo": texto_plano(titulo.group(1)) if titulo else "",
            "dia": texto_plano(dato("Fecha-dia")),
            "mes": texto_plano(dato("Fecha-mes")),
            "anio": texto_plano(dato("Fecha-anio")),
            "lugar": html.unescape(texto_plano(dato("Box-info"))),
        })
    return items


def armar_evento(item: dict, ahora: datetime) -> EventoCrudo | None:
    titulo, info = item["titulo"], item["lugar"]
    # "18:30 - Museo Zorrilla, José Luis Zorrilla de San Martín 96."
    hora = re.match(r"\s*(\d{1,2}):(\d{2})\s*-\s*", info)
    lugar = info[hora.end():] if hora else info
    if "museo" not in sin_tildes(f"{lugar} {titulo}") or "virtual" in sin_tildes(lugar):
        return None
    # "… esq. Zorrilla de San Martín (Canelones)": el departamento puede venir entre paréntesis.
    if not titulo or esta_cancelado(titulo) or menciona_otra_ciudad(re.sub(r"[().]", " ", lugar)):
        return None
    mes = mes_de(item["mes"].split("-")[0].strip())
    dia = re.match(r"\d{1,2}", item["dia"])
    if not mes or not dia or not item["anio"].isdigit():
        return None
    fecha = date(int(item["anio"]), mes, int(dia.group(0)))
    if fecha < ahora.date():
        return None
    # "Museo Gurvich (Sarandí 524). Museo Gurvich" / "Museo Zorrilla, José Luis Zorrilla de San Martín 96."
    partes = re.split(r"\s*[,(]\s*", lugar.strip(" ."), maxsplit=1)
    nombre = partes[0].strip(" .")
    direccion = partes[1].split(")")[0].strip(" .") if len(partes) > 1 else None
    inicio = datetime.combine(fecha, time(int(hora.group(1)), int(hora.group(2))) if hora else time(0, 0), tzinfo=ahora.tzinfo)
    plano = sin_tildes(titulo)
    rubro = next((r for r, patron in _RUBROS if patron.search(plano)), None)
    url = f"{BASE}{item['ruta']}"
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=item["ruta"].rsplit("/", 1)[-1],
        url=url,
        titulo=titulo,
        categoria=rubro or clasificar(titulo, por_defecto="otros"),
        lugar=LugarCrudo(nombre=nombre, direccion=direccion),
        funciones=[Funcion(inicio=inicio, sin_hora=not hora)],
        entradas=[Entrada(url=url, via=NOMBRE)],
        productor="Ministerio de Educación y Cultura",
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos = []
    for pagina in range(MAX_PAGINAS):
        items = leer_listado(cliente.texto(CALENDARIO if pagina == 0 else f"{CALENDARIO}?page={pagina}"))
        if not items:
            break
        eventos += [e for item in items if (e := armar_evento(item, ahora))]
    return eventos, []
