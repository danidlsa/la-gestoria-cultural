"""Portal de eventos de la Intendencia (eventos.montevideo.gub.uy): API JSON:API de Drupal.

En el portal, un "evento" es un paraguas (Encuentro de Murga Joven, Envejecimiento activo) y cada
"actividad" es lo que pasa en un lugar y una fecha. Se leen las actividades, con el paraguas como ciclo.
Algunos paraguas no tienen actividades cargadas y ponen el programa en un texto ("Próximas fechas":
"Sábado 7 de noviembre, desde las 16:00 h, en el Jardín Botánico."): de esos se lee cada línea.

Entra todo menos el deporte (decisión). Los talleres, cursos y clases van en su propia categoría. Las
actividades que se repiten se expanden en funciones; las que se repiten sin fecha de fin se descartan,
porque en el portal suelen ser actividades viejas o de vacaciones que nadie dio de baja.
La API solo responde desde Uruguay, así que esta fuente corre local (no en GitHub Actions).
"""

import html
import logging
import re
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from dateutil.rrule import rrulestr

from cartelera.categorias import clasificar, es_deporte, esta_cancelado
from cartelera.extraer import precio_de, recortar, texto_plano
from cartelera.geo import VARIOS_BARRIOS, sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import EventoCrudo, Funcion, LugarCrudo, Precio
from cartelera.scrapers.muestras import mes_de

NOMBRE = "portal_im"
SITIO = "https://eventos.montevideo.gub.uy"
API = f"{SITIO}/jsonapi/node/actividad"
API_EVENTOS = f"{SITIO}/jsonapi/node/evento"
POR_PAGINA = 25  # la API tarda unos 10 segundos por página con todo incluido
DIAS_ADELANTE = 180
MARGEN_PASADO = timedelta(hours=6)
MAXIMO_FUNCIONES = 60
# Una actividad en esta cantidad de lugares o más (un taller que recorre los barrios) va en una sola tarjeta.
MINIMO_PARA_JUNTAR_LUGARES = 5

CATEGORIAS = {
    "musica": ("musica", True),
    "carnaval": ("carnaval", True),
    "artes visuales": ("exposicion", True),
    "paseos": ("tour", True),
    "audiovisual": ("cine", True),
    # Artes escénicas mezcla teatro, danza, murga e infantiles: se afina por palabras clave.
    "artes escenicas": ("teatro", False),
    "literatura": ("charla", False),
}
EXCLUIDAS = {"deportes"}
_TALLER = re.compile(r"\b(taller(es)?|cursos?|clases?|escuelas?|workshops?)\b")
# "Murga Joven: domingo 15 de noviembre": el portal carga una actividad por fecha con la fecha en el título.
_FECHA_EN_TITULO = re.compile(
    r"[\s:,.-]+(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+\d{1,2}(\s+de\s+[a-záéíóú]+)?\s*$", re.I,
)

_INCLUIR = [
    "field_fechas_horarios", "field_fechas_horarios.field_donde", "field_categoria_listado",
    "field_evento_pertenece", "field_perfil_de_evento", "field_imagen_miniatura_listados.field_media_image",
]
_CAMPOS = {
    "node--actividad": "drupal_internal__nid,title,path,field_costo,field_detalle_costo,field_resumen,"
                       "field_contenido,field_categoria_listado,field_evento_pertenece,field_fechas_horarios,"
                       "field_perfil_de_evento,field_imagen_miniatura_listados",
    "paragraph--funciones": "field_fechas_horarios,field_donde",
    "node--lugar": "drupal_internal__nid,title,field_direccion,field_ubicacion",
    "node--evento": "title",
    "taxonomy_term--categoria": "name",
    "taxonomy_term--perfil_vento": "name",
    "media--image": "field_media_image",
    "file--file": "uri",
}
log = logging.getLogger(__name__)


def url_de_pagina() -> str:
    parametros = {
        "filter[status]": "1",  # sin este filtro la API devuelve también ítems despublicados vacíos
        "sort": "-changed.value",
        "page[limit]": str(POR_PAGINA),
        "include": ",".join(_INCLUIR),
        **{f"fields[{tipo}]": campos for tipo, campos in _CAMPOS.items()},
    }
    return f"{API}?{urlencode(parametros)}"


def url_de_paraguas(hoy: date) -> str:
    """Los eventos paraguas que siguen vigentes, con sus párrafos (ahí está el texto de las fechas)."""
    parametros = {
        "filter[status]": "1",
        "filter[vigente][condition][path]": "field_fechas.end_value",
        "filter[vigente][condition][operator]": ">=",
        "filter[vigente][condition][value]": hoy.isoformat(),
        "page[limit]": "50",
        "include": "field_parrafos_evento,field_categoria",
    }
    return f"{API_EVENTOS}?{urlencode(parametros)}"


def coordenadas(wkt: str | None) -> tuple[float | None, float | None]:
    """Punto de un campo geográfico WKT. Algunos lugares tienen lat y lon invertidas: se ordenan por rango."""
    lats, lons = [], []
    for a, b in re.findall(r"(-?\d+\.\d+)\s+(-?\d+\.\d+)", wkt or ""):
        a, b = float(a), float(b)
        lat, lon = (a, b) if -36 < a < -30 else (b, a)
        if -36 < lat < -30 and -59 < lon < -53:
            lats.append(lat)
            lons.append(lon)
    if not lats:
        return None, None
    return sum(lats) / len(lats), sum(lons) / len(lons)


def funciones_de(fechas: list[dict], ahora: datetime) -> list[Funcion] | None:
    """Funciones futuras de un paragraph--funciones. None si se repite sin fecha de fin."""
    desde, hasta = ahora - MARGEN_PASADO, ahora + timedelta(days=DIAS_ADELANTE)
    funciones = []
    for fecha in fechas:
        inicio = datetime.fromisoformat(fecha["value"])
        fin = datetime.fromisoformat(fecha["end_value"]) if fecha.get("end_value") else None
        duracion = fin - inicio if fin and fin > inicio else None
        regla = fecha.get("rrule")
        if regla:
            if "UNTIL=" not in regla and "COUNT=" not in regla:
                return None
            inicios = rrulestr(regla, dtstart=inicio).between(desde, hasta, inc=True)
        else:
            inicios = [inicio] if desde <= inicio <= hasta else []
        for comienzo in inicios[:MAXIMO_FUNCIONES]:
            comienzo = comienzo.astimezone(ahora.tzinfo)
            funciones.append(Funcion(inicio=comienzo, fin=comienzo + duracion if duracion else None))
    return funciones


def _categoria(nombre: str | None, titulo: str, resumen: str, publico: list[str]) -> tuple[str, bool]:
    """La categoría del portal, afinada con el público y el título (no con el texto largo, que menciona de
    todo: "una niña curiosa", "la historia de una familia de circo")."""
    if _TALLER.search(sin_tildes(titulo)):
        return "taller", True
    categoria, segura = CATEGORIAS.get(sin_tildes(nombre or ""), ("otros", False))
    if segura:
        return categoria, True
    if publico and all("nin" in sin_tildes(p) for p in publico):
        return "infantil", True
    afinada = clasificar(titulo, resumen, por_defecto=categoria)
    if categoria == "otros" or afinada in ("carnaval", "danza", "humor"):
        return afinada, False
    return categoria, False


def _precio(costo: str | None, detalle: str | None) -> Precio | None:
    if costo == "0":
        return Precio(desde=0, hasta=0, gratis=True)
    return precio_de(detalle) if detalle else None


class Indice:
    """Los recursos incluidos en la respuesta, para resolver las relaciones."""

    def __init__(self, incluidos: list[dict]):
        self._por_id = {i["id"]: i for i in incluidos}

    def de(self, relacion: dict | None) -> dict | None:
        datos = (relacion or {}).get("data")
        return self._por_id.get(datos["id"]) if isinstance(datos, dict) else None

    def todos(self, relacion: dict | None) -> list[dict]:
        datos = (relacion or {}).get("data") or []
        return [self._por_id[d["id"]] for d in datos if d["id"] in self._por_id]

    def imagen(self, relacion: dict | None) -> str | None:
        media = self.de(relacion)
        archivo = self.de(media["relationships"].get("field_media_image")) if media else None
        url = ((archivo or {}).get("attributes", {}).get("uri") or {}).get("url")
        return f"{SITIO}{url}" if url else None


def armar_eventos(actividad: dict, indice: Indice, ahora: datetime) -> list[EventoCrudo]:
    """Uno por lugar: algunas actividades se hacen en varios (una gira por los barrios)."""
    datos, rel = actividad["attributes"], actividad["relationships"]
    titulo = re.sub(r"\s+", " ", datos["title"]).strip()
    categoria_im = (indice.de(rel.get("field_categoria_listado")) or {}).get("attributes", {}).get("name")
    if sin_tildes(categoria_im or "") in EXCLUIDAS or esta_cancelado(titulo):
        return []
    if es_deporte(titulo):
        return []

    por_lugar: dict[str, tuple[dict, list[Funcion]]] = {}
    for parrafo in indice.todos(rel.get("field_fechas_horarios")):
        lugar = indice.de(parrafo["relationships"].get("field_donde"))
        if not lugar:
            continue
        funciones = funciones_de(parrafo["attributes"].get("field_fechas_horarios") or [], ahora)
        if funciones is None:
            return []
        por_lugar.setdefault(lugar["id"], (lugar, []))[1].extend(funciones)

    descripcion = texto_plano((datos.get("field_resumen") or {}).get("value"))
    contenido = texto_plano((datos.get("field_contenido") or {}).get("value"))
    publico = [p["attributes"]["name"] for p in indice.todos(rel.get("field_perfil_de_evento"))]
    categoria, segura = _categoria(categoria_im, titulo, descripcion, publico)
    paraguas = (indice.de(rel.get("field_evento_pertenece")) or {}).get("attributes", {}).get("title")
    nid = str(datos["drupal_internal__nid"])

    comunes = dict(
        fuente=NOMBRE,
        url=f"{SITIO}{datos['path']['alias']}" if datos.get("path", {}).get("alias") else f"{SITIO}/node/{nid}",
        titulo=titulo,
        categoria=categoria,
        categoria_segura=segura,
        precio=_precio(datos.get("field_costo"), datos.get("field_detalle_costo")),
        imagen_url=indice.imagen(rel.get("field_imagen_miniatura_listados")),
        productor="Intendencia de Montevideo",
        ciclo=paraguas.strip() if paraguas else None,
    )
    con_funciones = [(lugar, funciones) for lugar, funciones in por_lugar.values() if funciones]

    # En muchos barrios: una sola tarjeta, con el lugar de cada función en su `sala`.
    if len(con_funciones) >= MINIMO_PARA_JUNTAR_LUGARES:
        nombres = [lugar["attributes"]["title"].strip() for lugar, _ in con_funciones]
        todas = [
            funcion.model_copy(update={"sala": nombre})
            for nombre, (_, funciones) in zip(nombres, con_funciones) for funcion in funciones
        ]
        return [EventoCrudo(
            **comunes,
            id_externo=nid,
            descripcion_corta=recortar(f"En {len(nombres)} lugares: {', '.join(nombres)}. {contenido or descripcion}"),
            lugar=LugarCrudo(nombre=VARIOS_BARRIOS),
            funciones=sorted(todas, key=lambda f: f.inicio),
        )]

    eventos = []
    for lugar, funciones in con_funciones:
        lat, lon = coordenadas((lugar["attributes"].get("field_ubicacion") or {}).get("value"))
        eventos.append(EventoCrudo(
            **comunes,
            id_externo=nid if len(por_lugar) == 1 else f"{nid}-{lugar['attributes']['drupal_internal__nid']}",
            descripcion_corta=recortar(contenido or descripcion),
            lugar=LugarCrudo(
                nombre=lugar["attributes"]["title"].strip(),
                direccion=(lugar["attributes"].get("field_direccion") or "").strip() or None,
                lat=lat,
                lon=lon,
            ),
            funciones=sorted(funciones, key=lambda f: f.inicio),
        ))
    return eventos


# "Sábado 28 y domingo 29 de noviembre, desde las 16:00 h, Músicas Pioneras en Las Pioneras."
_DIA = r"(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)\s+\d{1,2}"
_LINEA_DE_FECHA = re.compile(
    rf"^(?P<dias>{_DIA}(?:\s*(?:,|y)\s*{_DIA})*)\s+de\s+(?P<mes>[a-z]+)(?:\s+de\s+\d{{4}})?"
    r"(?:,?\s*(?:desde\s+)?las\s+(?P<hora>\d{1,2})(?:[:.](?P<minuto>\d{2}))?\s*(?:h|hs|horas)?)?"
    r"(?:,\s*(?P<resto>.+?))?\.?$",
    re.I,
)


def _item_de_lista(texto_html: str) -> list[str]:
    return [re.sub(r"\s+", " ", html.unescape(texto_plano(li))).strip() for li in re.findall(r"<li[^>]*>(.*?)</li>", texto_html, re.S)]


def leer_linea_de_fecha(linea: str, anio_de: callable) -> tuple[list[date], time | None, str | None, str | None] | None:
    """(días, hora, subtítulo, lugar) de una línea del programa, o None si no es una línea de fecha."""
    plano = sin_tildes(linea)  # mismo largo que la línea: las posiciones sirven para cortar el original
    encontrada = _LINEA_DE_FECHA.match(plano)
    mes = mes_de(encontrada.group("mes")) if encontrada else None
    if not mes:
        return None
    dias = [date(anio_de(mes), mes, int(n)) for n in re.findall(r"\d{1,2}", encontrada.group("dias"))]
    hora = time(int(encontrada.group("hora")), int(encontrada.group("minuto") or 0)) if encontrada.group("hora") else None
    subtitulo = lugar = None
    if encontrada.group("resto"):
        resto = linea[encontrada.start("resto"):encontrada.end("resto")].strip()
        # "en el Jardín Botánico" / "Músicas Pioneras en Las Pioneras" (el artículo en mayúscula es parte del nombre).
        partes = re.match(r"^(?:(?P<sub>.+?)\s+)?en\s+(?:el\s+|la\s+)?(?P<lugar>.+)$", resto)
        if partes:
            subtitulo, lugar = partes.group("sub"), partes.group("lugar")
            lugar = lugar[:1].upper() + lugar[1:]
    return dias, hora, subtitulo, lugar


def eventos_de_paraguas(paraguas: dict, indice: Indice, ahora: datetime) -> list[EventoCrudo]:
    """Un evento por línea de fecha del texto de un paraguas sin actividades cargadas."""
    datos, rel = paraguas["attributes"], paraguas["relationships"]
    titulo = re.sub(r"\s+", " ", datos["title"]).strip()
    fechas = datos.get("field_fechas") or {}
    if not fechas.get("value") or esta_cancelado(titulo):
        return []
    inicio_ciclo = datetime.fromisoformat(fechas["value"])
    fin_ciclo = datetime.fromisoformat(fechas.get("end_value") or fechas["value"])
    # El año de cada fecha: el del ciclo que la contiene (un ciclo de noviembre a febrero cruza el año).
    anio_de = lambda mes: inicio_ciclo.year if mes >= inicio_ciclo.month or inicio_ciclo.year == fin_ciclo.year else fin_ciclo.year  # noqa: E731
    lineas = [
        linea for parrafo in indice.todos(rel.get("field_parrafos_evento")) if parrafo["type"] == "paragraph--texto"
        for linea in _item_de_lista((parrafo["attributes"].get("field_desc_componente") or {}).get("value") or "")
    ]
    lugar_general = texto_plano((datos.get("field_donde") or {}).get("value")) or None
    hora_general = inicio_ciclo.time() if inicio_ciclo.time() != time(0, 0) else None
    descripcion = " ".join(filter(None, [datos.get("field_subtitulo"), texto_plano((datos.get("field_bajada") or {}).get("value"))]))
    categoria_im = sin_tildes(next((c["attributes"]["name"] for c in indice.todos(rel.get("field_categoria"))), ""))
    if categoria_im in EXCLUIDAS or es_deporte(titulo):
        return []
    url = f"{SITIO}{datos['path']['alias']}" if datos.get("path", {}).get("alias") else f"{SITIO}/node/{datos['drupal_internal__nid']}"
    gratis = "entrada libre" in sin_tildes(descripcion) or "gratis" in sin_tildes(descripcion)

    eventos = []
    for linea in lineas:
        leida = leer_linea_de_fecha(linea, anio_de)
        if not leida:
            continue
        dias, hora, subtitulo, lugar = leida
        lugar = lugar or lugar_general
        hora = hora or hora_general
        funciones = [
            Funcion(inicio=datetime.combine(dia, hora or time(0, 0), tzinfo=ahora.tzinfo), sin_hora=hora is None)
            for dia in dias if dia >= ahora.date()
        ]
        if not lugar or not funciones:
            continue
        nombre = f"{titulo}: {subtitulo}" if subtitulo else titulo
        eventos.append(EventoCrudo(
            fuente=NOMBRE,
            id_externo=f"{datos['drupal_internal__nid']}-{dias[0].isoformat()}",
            url=url,
            titulo=nombre,
            categoria=clasificar(nombre, descripcion, por_defecto=CATEGORIAS.get(categoria_im, ("otros", False))[0]),
            descripcion_corta=recortar(descripcion),
            lugar=LugarCrudo(nombre=lugar),
            funciones=funciones,
            precio=Precio(desde=0, hasta=0, gratis=True) if gratis else None,
            productor="Intendencia de Montevideo",
            ciclo=titulo,
        ))
    return eventos


_TITULO_GENERICO = re.compile(r"(etapa|fecha|jornada|funci[oó]n|parte|d[ií]a)\b", re.I)


def titulo_sin_fecha(titulo: str) -> str:
    return _FECHA_EN_TITULO.sub("", titulo).strip() or titulo


def juntar_fechas(eventos: list[EventoCrudo]) -> list[EventoCrudo]:
    """Une las actividades que son el mismo evento en distintas fechas (mismo título sin la fecha y mismo lugar)."""
    por_clave: dict[tuple, EventoCrudo] = {}
    for evento in sorted(eventos, key=lambda e: int(e.id_externo.split("-")[0])):
        base = titulo_sin_fecha(evento.titulo)
        clave = (sin_tildes(base), sin_tildes(evento.lugar.nombre), evento.ciclo)
        if clave not in por_clave:
            por_clave[clave] = evento.model_copy(update={"titulo": base})
            continue
        unido = por_clave[clave]
        unido.funciones = sorted(unido.funciones + evento.funciones, key=lambda f: f.inicio)
    juntos = list(por_clave.values())
    for evento in juntos:
        # Títulos como "Etapa 5" no dicen nada sin el evento al que pertenecen.
        if evento.ciclo and _TITULO_GENERICO.match(evento.titulo) and len(evento.titulo.split()) <= 3:
            evento.titulo = f"{evento.ciclo}: {evento.titulo}"
    return juntos


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    url, paginas = url_de_pagina(), 0
    while url:
        respuesta = cliente.get(url).json()
        paginas += 1
        indice = Indice(respuesta.get("included") or [])
        for actividad in respuesta.get("data") or []:
            try:
                eventos += armar_eventos(actividad, indice, ahora)
            except Exception as error:  # noqa: BLE001 - una actividad rota no frena el resto
                errores.append(f"{actividad.get('id')}: {type(error).__name__}: {error}")
        siguiente = (respuesta.get("links") or {}).get("next", {}).get("href")
        # La API arma los enlaces con http://, y por ahí el servidor corta la conexión.
        url = siguiente.replace("http://", "https://", 1) if siguiente else None
    eventos = juntar_fechas(eventos)

    # Los paraguas sin actividades cargadas, con su programa en texto (Música en el Parque).
    try:
        respuesta = cliente.get(url_de_paraguas(ahora.date())).json()
        indice = Indice(respuesta.get("included") or [])
        con_actividades = {e.ciclo for e in eventos}
        for paraguas in respuesta.get("data") or []:
            if re.sub(r"\s+", " ", paraguas["attributes"]["title"]).strip() not in con_actividades:
                eventos += eventos_de_paraguas(paraguas, indice, ahora)
    except Exception as error:  # noqa: BLE001 - sin los paraguas, las actividades salen igual
        errores.append(f"paraguas: {type(error).__name__}: {error}")
    log.info("portal_im: %s páginas, %s eventos con fecha", paginas, len(eventos))
    return eventos, errores
