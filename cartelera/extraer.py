"""Utilidades para sacar datos estructurados de páginas HTML."""

import html
import json
import re
from datetime import date, timedelta

from cartelera.modelo import Precio

_SCRIPT_JSONLD = re.compile(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S | re.I)
_NEXT_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_ETIQUETA = re.compile(r"<[^>]+>")


def jsonld(pagina: str) -> list[dict]:
    """Todos los objetos JSON-LD de la página, aplanando listas y @graph."""
    objetos: list[dict] = []
    for bloque in _SCRIPT_JSONLD.findall(pagina):
        try:
            datos = json.loads(bloque)
        except json.JSONDecodeError:
            continue
        pendientes = datos if isinstance(datos, list) else [datos]
        while pendientes:
            item = pendientes.pop(0)
            if not isinstance(item, dict):
                continue
            if "@graph" in item:
                pendientes.extend(item["@graph"])
            else:
                objetos.append(item)
    return objetos


def jsonld_de_tipo(pagina: str, *tipos: str) -> list[dict]:
    return [o for o in jsonld(pagina) if o.get("@type") in tipos]


def payload_next(pagina: str) -> str:
    """El payload de React Server Components que Next.js mete en la página, ya decodificado."""
    partes = []
    for crudo in _NEXT_CHUNK.findall(pagina):
        try:
            partes.append(json.loads(f'"{crudo}"'))
        except json.JSONDecodeError:
            continue
    return "".join(partes)


def objeto_json_que_contiene(texto: str, clave: str) -> dict | None:
    """Decodifica el objeto JSON más chico que contiene `"clave":`, buscando hacia atrás la llave que lo abre."""
    posicion = texto.find(f'"{clave}":')
    if posicion < 0:
        return None
    profundidad = 0
    for inicio in range(posicion, -1, -1):
        caracter = texto[inicio]
        if caracter == "}":
            profundidad += 1
        elif caracter == "{":
            if profundidad == 0:
                try:
                    objeto, _ = json.JSONDecoder().raw_decode(texto[inicio:])
                    return objeto
                except json.JSONDecodeError:
                    return None
            profundidad -= 1
    return None


def texto_plano(fragmento: str | None) -> str:
    if not fragmento:
        return ""
    sin_etiquetas = _ETIQUETA.sub(" ", html.unescape(fragmento))
    return re.sub(r"\s+", " ", html.unescape(sin_etiquetas)).strip()


def recortar(texto: str | None, maximo: int = 300) -> str | None:
    """Recorta en el último espacio antes del máximo, para no republicar textos largos."""
    texto = texto_plano(texto)
    if not texto:
        return None
    if len(texto) <= maximo:
        return texto
    return texto[:maximo].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"


def meta(pagina: str, propiedad: str) -> str | None:
    patron = rf'<meta[^>]+(?:property|name)="{re.escape(propiedad)}"[^>]+content="([^"]*)"'
    encontrado = re.search(patron, pagina)
    return html.unescape(encontrado.group(1)) if encontrado else None


def precio_de(localidades: str) -> Precio | None:
    """Precio a partir de un texto como "$ 600 - Promo 2 x $ 800" o "Entrada libre"."""
    if re.search(r"gratis|entrada libre|sin costo|gratuit", localidades, re.I):
        return Precio(desde=0, hasta=0, gratis=True)
    # El primer monto es el general; los que van después de "promo", "2 x" o "socio" son descuentos.
    generales = []
    for parte in re.split(r"\s+-\s+|\.\s|;", localidades):
        if re.search(r"promo|2\s*x|socio|diaria|descuento|%", parte, re.I):
            continue
        generales += [float(m.replace(".", "")) for m in re.findall(r"\$\s*([\d.]+)", parte)]
    if not generales:
        return None
    return Precio(desde=min(generales), hasta=max(generales))


# Una fecha sin año que pasó hace menos que esto ya pasó; si pasó hace más, es del año que viene
# ("10 de abril" leído en octubre). Un mes deja afuera las funciones recién pasadas de una temporada.
VENTANA_FECHA_PASADA = timedelta(days=30)


def fecha_sin_anio(dia: int, mes: int, hoy: date) -> date | None:
    """La fecha de ese día y mes más probable a partir de hoy, o None si ya pasó (o no existe)."""
    try:
        candidata = date(hoy.year, mes, dia)
    except ValueError:
        return None
    if candidata >= hoy - timedelta(days=1):
        return candidata
    if hoy - candidata <= VENTANA_FECHA_PASADA:
        return None
    try:
        return date(hoy.year + 1, mes, dia)
    except ValueError:
        return None

