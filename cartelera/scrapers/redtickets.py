"""RedTickets: la portada y las categorías listan eventos; cada detalle trae categoría, ciudad y funciones en JSON."""

import html
import json
import logging
import re
from datetime import datetime, time, timedelta
from pathlib import Path

from cartelera.beneficios import beneficios_de_entradas
from cartelera.categorias import categoria_por_lugar, clasificar, es_deporte, esta_cancelado
from cartelera.extraer import meta, objeto_json_que_contiene, recortar
from cartelera.geo import en_montevideo, sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo, Precio

NOMBRE = "redtickets"
BASE = "https://www.redtickets.uy"

# Categorías de RedTickets traducidas a las nuestras. None = fuera de la cartelera.
CATEGORIAS = {
    "1": "infantil", "3": "musica", "5": "charla", "6": "teatro", "9": "fiesta", "10": "carnaval",
    "12": "musica", "30": "festival", "32": "tour", "45": "exposicion", "87": "cine", "99": "musica",
    "2": None, "4": None, "8": None, "13": None, "28": None,  # deportes, cursos, fútbol, empresarial, afiliados
}
MARGEN_PASADO = timedelta(hours=6)
# Tipos de entrada que no son el precio general: cortesías, beneficios y descuentos de clubes.
_NO_GENERAL = re.compile(r"cortes|invitac|acredit|socio|2x1|% ?off|descuento|beneficio|libre|\bsua\b", re.I)
_ENLACE_EVENTO = re.compile(r"/evento/[^\"'/\s]+/(\d+)/")
log = logging.getLogger(__name__)


class Excluido(Exception):
    """El evento existe pero no va en la cartelera (deporte, curso, otra ciudad)."""


def ids_de_listado(pagina: str) -> dict[str, str]:
    """{id: ruta} de los eventos enlazados en una portada o página de categoría."""
    encontrados = {}
    for coincidencia in _ENLACE_EVENTO.finditer(pagina):
        encontrados.setdefault(coincidencia.group(1), coincidencia.group(0))
    return encontrados


def _punto(geopoint: str | None) -> tuple[float | None, float | None]:
    """'POINT (-56.181082 -34.90403)' -> (lat, lon)."""
    encontrado = re.match(r"POINT \((-?[\d.]+) (-?[\d.]+)\)", geopoint or "")
    if not encontrado:
        return None, None
    return float(encontrado.group(2)), float(encontrado.group(1))


def _categoria(categorias: list[dict]) -> str | None:
    """La primera categoría de RedTickets que tenga traducción. Lanza Excluido si alguna es excluida."""
    elegida = None
    for categoria in categorias or []:
        clave = str(categoria.get("id"))
        if clave in CATEGORIAS and CATEGORIAS[clave] is None:
            raise Excluido(f"categoría {categoria.get('name')}")
        elegida = elegida or CATEGORIAS.get(clave)
    return elegida


def _funciones(fechas: list[dict], ahora: datetime) -> tuple[list[Funcion], list[tuple[str, float]]]:
    """Las funciones futuras y los (nombre, precio) de sus tipos de entrada."""
    funciones, precios = [], []
    for fecha in fechas:
        dia = datetime.fromisoformat(fecha["date"]).date()
        for horario in fecha.get("Times") or [{}]:
            hora = re.match(r"(\d{1,2})[:.](\d{2})", horario.get("caption", ""))
            inicio = datetime.combine(
                dia, time(int(hora.group(1)), int(hora.group(2))) if hora else time(0, 0), tzinfo=ahora.tzinfo,
            )
            vencida = inicio < ahora - MARGEN_PASADO if hora else dia < ahora.date()
            if vencida:
                continue
            funciones.append(Funcion(
                inicio=inicio,
                sin_hora=hora is None,
                agotada=bool(fecha.get("soldOut") or horario.get("soldOut")),
            ))
            for entrada in horario.get("Tickets") or []:
                try:
                    precios.append((entrada.get("caption") or "", float(entrada["price"])))
                except (KeyError, TypeError, ValueError):
                    pass
    return funciones, precios


def parsear_evento(pagina: str, url: str, id_externo: str, ahora: datetime) -> EventoCrudo | None:
    """Arma el evento con sus funciones futuras. None si no le queda ninguna; Excluido si no va."""
    ficha = objeto_json_que_contiene(pagina, "Producer") or {}
    compra = (objeto_json_que_contiene(pagina, "Dates") or {})
    info = ficha.get("Evt") or {}
    if not compra.get("Dates"):
        return None

    ciudad = info.get("cityname") or ""
    if ciudad and sin_tildes(ciudad) != "montevideo":
        raise Excluido(f"ciudad {ciudad}")
    categoria = _categoria(info.get("Categories"))
    funciones, precios = _funciones(compra["Dates"], ahora)
    if not funciones:
        return None

    ubicacion = ficha.get("Location") or {}
    lat, lon = _punto(ubicacion.get("GeoPoint"))
    direccion = html.unescape(ubicacion.get("Address") or info.get("locationInfo") or "").strip()
    nombre_lugar = html.unescape(info.get("locationName") or direccion.split(" - ")[0]).strip()
    if " - " in direccion:
        direccion = direccion.split(" - ", 1)[1].strip()
    titulo = html.unescape(compra.get("name") or info.get("name") or meta(pagina, "og:title") or "").strip()
    descripcion = info.get("description") or meta(pagina, "og:description")
    generales = [precio for nombre, precio in precios if not _NO_GENERAL.search(nombre)] or [p for _, p in precios]
    gratis = bool(compra.get("isFree") or info.get("isFree")) or (bool(generales) and max(generales) == 0)
    # Una entrada a $0 entre otras pagas suele ser para menores: no es el precio "desde".
    generales = [p for p in generales if p > 0] or generales
    if es_deporte(titulo):
        raise Excluido("deporte")
    if esta_cancelado(titulo):
        raise Excluido("cancelado")

    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=id_externo,
        url=url,
        titulo=titulo,
        categoria=categoria or clasificar(titulo, descripcion, por_defecto=categoria_por_lugar(nombre_lugar)),
        categoria_segura=categoria is not None,
        descripcion_corta=recortar(descripcion),
        lugar=LugarCrudo(nombre=nombre_lugar or "Sin lugar", direccion=direccion or None, lat=lat, lon=lon),
        funciones=sorted(funciones, key=lambda f: f.inicio),
        precio=Precio(
            desde=min(generales) if generales else None, hasta=max(generales) if generales else None, gratis=gratis,
        ) if generales or gratis else None,
        entradas=[Entrada(url=url, via=NOMBRE)],
        beneficios=beneficios_de_entradas([nombre for nombre, _ in precios], url),
        imagen_url=compra.get("imageUrl") or info.get("imageUrl") or meta(pagina, "og:image"),
        productor=((ficha.get("Producer") or {}).get("Name") or "").strip() or None,
    )


# Categorías del listado (por nombre) que no van en la cartelera: se descartan sin abrir el detalle.
CATEGORIAS_EXCLUIDAS = {"deportes", "cursos", "futbol", "empresarial", "afiliados"}
MAX_PAGINAS = 80
# El detalle de cada evento se vuelve a pedir como mucho una vez por este período; entre medio se
# reusa lo que se trajo antes. Los eventos de otras ciudades se recuerdan para no volver a abrirlos.
REVISAR_CADA = timedelta(hours=20)
REVISAR_EXCLUIDOS_CADA = timedelta(days=7)
CACHE = Path("datos/cache/redtickets.json")


def listado_completo(cliente: Cliente) -> dict[str, str]:
    """{id: ruta} de todo el catálogo, recorriendo la búsqueda paginada (24 eventos por página)."""
    rutas: dict[str, str] = {}
    for numero in range(MAX_PAGINAS):
        pagina = cliente.texto(f"{BASE}/busqueda?,,,0,{numero}")
        nuevos = {i: r for i, r in ids_de_listado(pagina).items() if i not in rutas}
        if not nuevos:
            break
        for item in _items_de_busqueda(pagina):
            if sin_tildes(item.get("Category") or "") in CATEGORIAS_EXCLUIDAS:
                nuevos.pop(str(item.get("Id")), None)
        rutas.update(nuevos)
    return rutas


def _items_de_busqueda(pagina: str) -> list[dict]:
    decodificador = json.JSONDecoder()
    items = []
    for coincidencia in re.finditer(r'\{"SecuentialId":', pagina):
        try:
            items.append(decodificador.raw_decode(pagina, coincidencia.start())[0])
        except json.JSONDecodeError:
            continue
    return items


def _cargar_cache() -> dict[str, dict]:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _vigente_otra_vez(evento: EventoCrudo, ahora: datetime) -> EventoCrudo | None:
    """Un evento traído en una corrida anterior, sin las funciones que ya pasaron."""
    funciones = [
        f for f in evento.funciones
        if not (f.inicio.date() < ahora.date() if f.sin_hora else f.inicio < ahora - MARGEN_PASADO)
    ]
    return evento.model_copy(update={"funciones": funciones}) if funciones else None


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    from cartelera.scrapers.base import cargar  # evita un import circular

    rutas = listado_completo(cliente)
    log.info("redtickets: %s eventos en el catálogo (sin categorías excluidas)", len(rutas))
    anterior = {e.id_externo: e for e in (cargar(NOMBRE).eventos if cargar(NOMBRE) else [])}
    cache = _cargar_cache()

    eventos, errores, excluidos, reusados = [], [], 0, 0
    for id_externo, ruta in rutas.items():
        visto = cache.get(id_externo, {})
        revisado = datetime.fromisoformat(visto["revisado"]) if visto.get("revisado") else None
        if revisado and visto.get("excluido") and ahora - revisado < REVISAR_EXCLUIDOS_CADA:
            excluidos += 1
            continue
        if revisado and id_externo in anterior and ahora - revisado < REVISAR_CADA:
            evento = _vigente_otra_vez(anterior[id_externo], ahora)
            if evento:
                eventos.append(evento)
            reusados += 1
            continue

        url = f"{BASE}{ruta}"
        try:
            evento = parsear_evento(cliente.texto(url), url, id_externo, ahora)
        except Excluido as motivo:
            excluidos += 1
            cache[id_externo] = {"revisado": ahora.isoformat(), "excluido": str(motivo)}
            continue
        except Exception as error:  # noqa: BLE001 - una página rota no frena el resto
            errores.append(f"{url}: {type(error).__name__}: {error}")
            continue
        cache[id_externo] = {"revisado": ahora.isoformat(), "excluido": None}
        if evento and en_montevideo(evento.lugar.lat, evento.lugar.lon):
            eventos.append(evento)

    # Se olvida lo que ya no está en el catálogo.
    cache = {i: v for i, v in cache.items() if i in rutas}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=0), encoding="utf-8")
    log.info("redtickets: %s eventos (%s reusados de la corrida anterior), %s excluidos, %s errores",
             len(eventos), reusados, excluidos, len(errores))
    return eventos, errores
