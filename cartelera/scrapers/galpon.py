"""Teatro El Galpón: cada obra tiene su ficha con las funciones por día, sala y horario.

Casi todo se vende por RedTickets y cada función enlaza ahí, así que el cruce es exacto. El Galpón
suma la duración (para la hora de fin), la sala interna y las promociones escritas en la ficha.
"""

import html
import re
from datetime import datetime, time, timedelta

from cartelera.beneficios import beneficios_de_entradas
from cartelera.categorias import clasificar, esta_cancelado
from cartelera.extraer import meta, recortar, texto_plano
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo, Precio

NOMBRE = "galpon"
BASE = "https://www.teatroelgalpon.org.uy"
LUGAR = LugarCrudo(nombre="Teatro El Galpón", direccion="Av. 18 de Julio 1618", lat=-34.90403, lon=-56.181082)
_DIA = re.compile(r'<li\s+data-day="(\d{4}-\d{2}-\d{2})"\s+class="per_day"(.*?)</li>\s*(?=<li\s+data-day|</ol>)', re.S)


def _campo(texto: str, nombre: str) -> str | None:
    encontrado = re.search(rf"{nombre}:\s*(.+?)\s*(?:Autor|Dirección|Elenco|Funciones|Sala|Entradas|Duración|Calificación|Inicio|Seleccionar):", texto)
    return encontrado.group(1).strip() if encontrado else None


def parsear_ficha(pagina: str, url: str, ahora: datetime) -> EventoCrudo | None:
    titulo = re.search(r"<title>\s*(.+?)\s*-\s*Teatro El Galp", pagina)
    titulo = html.unescape(titulo.group(1)).strip() if titulo else None
    if not titulo or esta_cancelado(titulo):
        return None
    texto = texto_plano(pagina)
    duracion = re.search(r"Duración:\s*(\d+)\s*min", texto)
    entradas = _campo(texto, "Entradas") or ""

    funciones, compras = [], []
    for dia, bloque in _DIA.findall(pagina):
        sala = re.search(r'<strong class="sala">SALA</strong>\s*([^<]+)', bloque)
        compra = re.search(r'class="adquirir-localidad">\s*<a href="([^"]+)"', bloque)
        if compra:
            compras.append(compra.group(1))
        for hora, minuto in re.findall(r"<li>\s*(\d{1,2})[:.](\d{2})\s*</li>", bloque):
            inicio = datetime.combine(datetime.fromisoformat(dia).date(), time(int(hora), int(minuto)), tzinfo=ahora.tzinfo)
            if inicio < ahora - timedelta(hours=6):
                continue
            funciones.append(Funcion(
                inicio=inicio,
                fin=inicio + timedelta(minutes=int(duracion.group(1))) if duracion else None,
                sala=f"Sala {html.unescape(sala.group(1)).strip()}" if sala else None,
            ))
    if not funciones:
        return None

    generales = [float(m.replace(".", "")) for m in re.findall(r"Generales?\s*\$\s*([\d.]+)", entradas)]
    descripcion = meta(pagina, "og:description")
    compras = list(dict.fromkeys(compras))
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=url.rstrip("/").rsplit("/", 1)[1],
        url=url,
        titulo=titulo,
        categoria=clasificar(titulo, descripcion, por_defecto="teatro"),
        descripcion_corta=recortar(descripcion),
        lugar=LUGAR,
        funciones=sorted(funciones, key=lambda f: f.inicio),
        precio=Precio(desde=min(generales), hasta=max(generales)) if generales else None,
        entradas=[Entrada(url=c, via="redtickets" if "redtickets" in c else NOMBRE) for c in compras] or [Entrada(url=url, via=NOMBRE)],
        beneficios=beneficios_de_entradas(re.split(r"\.\s+|,\s+", entradas), url),
        imagen_url=meta(pagina, "og:image"),
        productor=(re.search(r"(Producción de .+?)\s+(?:Autor|Dirección|Elenco):", texto) or [None, "Teatro El Galpón"])[1].strip(),
        enlaces=compras,
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    listado = cliente.texto(f"{BASE}/espectaculos/")
    urls = list(dict.fromkeys(re.findall(r'href="(https://www\.teatroelgalpon\.org\.uy/espectaculos/[a-z0-9-]+/)"', listado)))
    eventos, errores = [], []
    for url in urls:
        try:
            evento = parsear_ficha(cliente.texto(url), url, ahora)
        except Exception as error:  # noqa: BLE001 - una ficha rota no frena el resto
            errores.append(f"{url}: {type(error).__name__}: {error}")
            continue
        if evento:
            eventos.append(evento)
    return eventos, errores
