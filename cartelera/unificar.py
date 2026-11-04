"""Une los resultados de todas las fuentes en una sola cartelera (ver docs/diseno.md)."""

import hashlib
import json
import logging
import math
import re
import tomllib
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from rapidfuzz import fuzz

from cartelera.etiquetas import etiquetar
from cartelera.generos import BuscadorDeGeneros
from cartelera.geocodificar import Geocodificador
from cartelera.geo import sin_tildes
from cartelera.modelo import Ciclo, Evento, EventoCrudo, Funcion, Lugar, Precio, Procedencia, ResultadoFuente
from cartelera.scrapers.base import DIR_FUENTES, MONTEVIDEO

DIR_DATOS = Path("datos")
ALIAS = Path("config/lugares_alias.toml")
# Prioridad al elegir qué dato mostrar: sala oficial > ticketera > cartelera > productora > beneficios.
PRIORIDAD = {
    "sodre": 4, "cinemateca": 4, "solis": 4, "teatro_de_verano": 4, "galpon": 4, "zitarrosa": 4, "sala_del_museo": 4,
    "museos_im": 4, "mnav": 4, "torres_garcia": 4, "gurvich": 4, "mapi": 4, "salacamacua": 4,
    "tickantel": 3, "redtickets": 3, "ticketmaster_uy": 3, "portal_im": 3, "fever": 3, "mec_museos": 3,
    "mientrada": 3, "cobraticket": 3,
    "cartelera_mvd": 2, "corchea": 2, "gaucho": 2, "piano_piano": 2, "ladiaria": 1,
}
MARGEN_PASADO = timedelta(hours=6)
DISTANCIA_MISMO_LUGAR_M = 120
log = logging.getLogger(__name__)


# --- Lugares -------------------------------------------------------------------------------------

def normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", sin_tildes(texto))).strip()


def slug(texto: str) -> str:
    return normalizar(texto).replace(" ", "-") or "lugar"


# Palabras genéricas que no distinguen una sala de otra: se ignoran al comparar nombres.
_GENERICAS = {
    "teatro", "sala", "salas", "espacio", "centro", "cultural", "museo", "escuela", "club", "bar", "auditorio",
    "de", "del", "la", "el", "los", "las", "y", "artes", "montevideo", "uruguay",
}
SIMILITUD_MISMO_LUGAR = 90


def separar_sala(nombre: str) -> tuple[str, str | None]:
    """'El Galpón - Sala Cero' -> ('El Galpón', 'Sala Cero'). Si no hay sala interna, la sala es None."""
    partes = re.split(r"\s+[-–|]\s+", nombre, maxsplit=1)
    if len(partes) == 2 and re.match(r"(?i)sala\b", partes[1].strip()):
        return partes[0].strip(), partes[1].strip()
    return nombre, None


def nombre_distintivo(nombre: str) -> str:
    """Lo que distingue a una sala: 'Teatro MANDRÁGORA Escuela de Artes' -> 'mandragora'."""
    return " ".join(p for p in normalizar(nombre).split() if p not in _GENERICAS)


def distancia_m(a: Lugar, lat: float, lon: float) -> float:
    if a.lat is None or a.lon is None:
        return math.inf
    dy = (a.lat - lat) * 111_320
    dx = (a.lon - lon) * 111_320 * math.cos(math.radians(lat))
    return math.hypot(dx, dy)


class Catalogo:
    """Asigna un lugar del catálogo a cada lugar crudo, por alias, por nombre o por cercanía."""

    def __init__(self, alias: list[dict]):
        self.lugares: dict[str, Lugar] = {}
        self._por_nombre: dict[str, str] = {}
        # Lugares que se asignan solo por su nombre exacto, nunca por parecido o cercanía.
        self._solo_por_nombre: set[str] = set()
        for entrada in alias:
            lugar = Lugar(
                id=entrada["id"], nombre=entrada["nombre"], alias=entrada.get("alias", []),
                direccion=entrada.get("direccion"), lat=entrada.get("lat"), lon=entrada.get("lon"),
            )
            self.lugares[lugar.id] = lugar
            if entrada.get("solo_por_nombre"):
                self._solo_por_nombre.add(lugar.id)
            for nombre in [lugar.nombre, *lugar.alias]:
                self._por_nombre[normalizar(nombre)] = lugar.id

    def _por_parecido(self, nombre: str, lat: float | None, lon: float | None) -> str | None:
        """Una sala ya conocida con un nombre equivalente, sin palabras genéricas de por medio."""
        distintivo = nombre_distintivo(nombre)
        if len(distintivo) < 4:
            return None
        for lugar in self.lugares.values():
            if lugar.id in self._solo_por_nombre:
                continue
            for candidato in [lugar.nombre, *lugar.alias]:
                otro = nombre_distintivo(candidato)
                # token_sort y no token_set: "solis" no tiene que unirse con "vieja farmacia solis".
                if len(otro) < 4 or fuzz.token_sort_ratio(distintivo, otro) < SIMILITUD_MISMO_LUGAR:
                    continue
                # Mismo nombre pero lejos (más de 1 km): son salas distintas.
                if lat is not None and lugar.lat is not None and distancia_m(lugar, lat, lon) > 1000:
                    continue
                return lugar.id
        return None

    def asignar(self, nombre: str, direccion: str | None, lat: float | None, lon: float | None) -> str:
        nombre, _sala = separar_sala(nombre)
        clave = normalizar(nombre)
        lugar_id = self._por_nombre.get(clave) or self._por_parecido(nombre, lat, lon)
        if lugar_id is None and lat is not None and lon is not None:
            cercanos = [
                l for l in self.lugares.values()
                if l.id not in self._solo_por_nombre and distancia_m(l, lat, lon) <= DISTANCIA_MISMO_LUGAR_M
                and fuzz.token_set_ratio(clave, normalizar(l.nombre)) >= 60
            ]
            if cercanos:
                lugar_id = min(cercanos, key=lambda l: distancia_m(l, lat, lon)).id
        if lugar_id is None:
            lugar_id = slug(nombre)
            while lugar_id in self.lugares:
                lugar_id += "-2"
            self.lugares[lugar_id] = Lugar(id=lugar_id, nombre=nombre)
        self._por_nombre.setdefault(clave, lugar_id)

        lugar = self.lugares[lugar_id]
        # Completa lo que falte (los lugares de la lista de alias empiezan sin dirección ni coordenadas).
        if lugar.lat is None and lat is not None:
            lugar.lat, lugar.lon = lat, lon
        if lugar.direccion is None and direccion:
            lugar.direccion = direccion
        if nombre != lugar.nombre and nombre not in lugar.alias:
            lugar.alias.append(nombre)
        return lugar_id


def cargar_alias(ruta: Path = ALIAS) -> list[dict]:
    if not ruta.exists():
        return []
    return tomllib.loads(ruta.read_text(encoding="utf-8")).get("lugar", [])


# --- Deduplicación -------------------------------------------------------------------------------

_CLAVES_DE_URL = [
    ("redtickets", re.compile(r"redtickets\.uy/evento/[^/]+/(\d+)")),
    # El formato viejo de los links de RedTickets, que usan algunas salas: /servlet/com.redtickets.frontend.wevent?,33806
    ("redtickets", re.compile(r"redtickets\.uy/+servlet/com\.redtickets\.frontend\.wevent\?,?(\d+)")),
    # /ng/espectaculo/40021761/…, /ng/espectaculo/alta-demanda/40021784/…, /inicio/espectaculo/40020151/…,
    # /inicio/alta_demanda/40020997
    ("tickantel", re.compile(r"tickantel\.com\.uy/(?:ng|inicio)/(?:espectaculo/)?(?:alta[-_]demanda/)?(\d{7,9})")),
    ("ticketmaster_uy", re.compile(r"ticketmaster\.uy/event/([\w-]+)")),
    ("mientrada", re.compile(r"mientrada\.com\.uy/evento/[\w-]*-(\d+)(?![\w-])")),
    ("cobraticket", re.compile(r"cobraticket\.uy/e/[\w-]*-(\d+)(?![\w-])")),
    # Las productoras enlazan a la ficha del Antel Arena (la venta es por Tickantel).
    ("antel_arena", re.compile(r"antelarena\.com\.uy/events/detail/([\w-]+)")),
]


def clave_de_url(url: str) -> str | None:
    """'https://redtickets.uy/evento/X/34406/' -> 'redtickets:34406'."""
    for fuente, patron in _CLAVES_DE_URL:
        encontrado = patron.search(url)
        if encontrado:
            return f"{fuente}:{encontrado.group(1)}"
    return None


def titulo_comparable(titulo: str) -> str:
    sin_parentesis = re.sub(r"\([^)]*\)", " ", titulo)
    return normalizar(re.sub(r"\b(presenta|presentan|en concierto)\b", " ", sin_tildes(sin_parentesis)))


def titulos_parecidos(a: str, b: str) -> bool:
    """Mismo título salvo detalles. Que uno contenga al otro cuenta solo si el más corto tiene 3+ palabras."""
    a, b = titulo_comparable(a), titulo_comparable(b)
    if fuzz.token_sort_ratio(a, b) >= 88:
        return True
    corto, largo = sorted((a, b), key=len)
    return len(corto.split()) >= 3 and f" {corto} " in f" {largo} "


def _compatibles(a: EventoCrudo, b: EventoCrudo, misma_sala: bool) -> bool:
    """¿Pueden ser el mismo evento? Misma sala, o títulos que comparten lo esencial."""
    return misma_sala or fuzz.token_set_ratio(titulo_comparable(a.titulo), titulo_comparable(b.titulo)) >= 60


class _Conjuntos:
    def __init__(self, n: int):
        self.padre = list(range(n))

    def raiz(self, i: int) -> int:
        while self.padre[i] != i:
            self.padre[i] = self.padre[self.padre[i]]
            i = self.padre[i]
        return i

    def unir(self, a: int, b: int) -> None:
        self.padre[self.raiz(a)] = self.raiz(b)


def agrupar(crudos: list[EventoCrudo], lugar_de: list[str]) -> list[list[int]]:
    """Índices de `crudos` agrupados por evento real."""
    conjuntos = _Conjuntos(len(crudos))
    dueno: dict[str, int] = {}

    # 1. Coincidencia exacta: el mismo ID de ticketera, propio o enlazado. Un enlace puede estar mal (un
    # beneficio de una obra que enlaza a la entrada de otra), así que además tienen que compartir la sala
    # o parecerse en el título.
    for i, crudo in enumerate(crudos):
        claves = {f"{crudo.fuente}:{crudo.id_externo}"}
        claves.update(c for c in map(clave_de_url, [crudo.url, *crudo.enlaces, *(e.url for e in crudo.entradas)]) if c)
        for clave in claves:
            if clave not in dueno:
                dueno[clave] = i
            elif _compatibles(crudos[i], crudos[dueno[clave]], lugar_de[i] == lugar_de[dueno[clave]]):
                conjuntos.unir(i, dueno[clave])

    # 2. Coincidencia difusa: mismo lugar, alguna función el mismo día y títulos parecidos.
    por_lugar: dict[str, list[int]] = defaultdict(list)
    for i, lugar_id in enumerate(lugar_de):
        por_lugar[lugar_id].append(i)
    for indices in por_lugar.values():
        for posicion, i in enumerate(indices):
            dias_i = {f.inicio.date() for f in crudos[i].funciones}
            for j in indices[posicion + 1:]:
                if crudos[i].fuente == crudos[j].fuente or conjuntos.raiz(i) == conjuntos.raiz(j):
                    continue
                if not dias_i & {f.inicio.date() for f in crudos[j].funciones}:
                    continue
                if titulos_parecidos(crudos[i].titulo, crudos[j].titulo):
                    conjuntos.unir(i, j)

    grupos: dict[int, list[int]] = defaultdict(list)
    for i in range(len(crudos)):
        grupos[conjuntos.raiz(i)].append(i)
    return list(grupos.values())


# --- Fusión --------------------------------------------------------------------------------------

def _fusionar_funciones(crudos: list[EventoCrudo]) -> list[Funcion]:
    por_inicio: dict[datetime, list[Funcion]] = defaultdict(list)
    for crudo in crudos:
        for funcion in crudo.funciones:
            por_inicio[funcion.inicio.replace(second=0, microsecond=0)].append(funcion)
    # Un día "sin hora" sobra si otra fuente informa ese mismo día con horario (pero se conserva su sala).
    dias_con_hora = {i.date() for i, vs in por_inicio.items() if not all(f.sin_hora for f in vs)}
    sala_del_dia = {i.date(): f.sala for i, vs in por_inicio.items() for f in vs if f.sala}
    por_inicio = {i: vs for i, vs in por_inicio.items() if not (all(f.sin_hora for f in vs) and i.date() in dias_con_hora)}
    fusionadas = []
    for inicio, versiones in sorted(por_inicio.items()):
        fusionadas.append(Funcion(
            inicio=inicio,
            fin=next((f.fin for f in versiones if f.fin), None),
            sin_hora=all(f.sin_hora for f in versiones),
            sala=next((f.sala for f in versiones if f.sala), None) or sala_del_dia.get(inicio.date()),
            # Cada ticketera vende su propio cupo: está agotada solo si todas lo dicen.
            agotada=all(f.agotada for f in versiones),
        ))
    return fusionadas


def _fusionar_precio(crudos: list[EventoCrudo]) -> Precio | None:
    precios = [c.precio for c in crudos if c.precio]
    if not precios:
        return None
    desdes = [p.desde for p in precios if p.desde is not None]
    hastas = [p.hasta for p in precios if p.hasta is not None]
    return Precio(
        desde=min(desdes) if desdes else None,
        hasta=max(hastas) if hastas else None,
        moneda=precios[0].moneda,
        gratis=all(p.gratis for p in precios),
    )


def fusionar(crudos: list[EventoCrudo], lugar_id: str, corridas: dict[str, datetime], ahora: datetime) -> Evento:
    principal = max(crudos, key=lambda c: (PRIORIDAD.get(c.fuente, 1), len(c.funciones)))
    con_categoria_segura = [c for c in crudos if c.categoria_segura]
    claves = sorted(f"{c.fuente}:{c.id_externo}" for c in crudos)
    # Un enlace por destino: la misma página de Tickantel puede llegar con distintos formatos de URL.
    entradas = {}
    for entrada in (e for c in sorted(crudos, key=lambda c: -PRIORIDAD.get(c.fuente, 1)) for e in c.entradas):
        entradas.setdefault(clave_de_url(entrada.url) or entrada.url, entrada)
    beneficios = {b.programa: b for c in crudos for b in c.beneficios}
    return Evento(
        id="ev_" + hashlib.sha1(claves[0].encode()).hexdigest()[:10],
        titulo=principal.titulo,
        categoria=(con_categoria_segura[0] if con_categoria_segura else principal).categoria,
        descripcion_corta=principal.descripcion_corta or next((c.descripcion_corta for c in crudos if c.descripcion_corta), None),
        lugar_id=lugar_id,
        funciones=_fusionar_funciones(crudos),
        precio=_fusionar_precio(crudos),
        entradas=list(entradas.values()),
        beneficios=list(beneficios.values()),
        imagen_url=principal.imagen_url or next((c.imagen_url for c in crudos if c.imagen_url), None),
        ciclo_nombre=next((c.ciclo for c in crudos if c.ciclo), None),
        muestra=any(c.muestra for c in crudos),
        hasta=max((c.hasta for c in crudos if c.hasta), default=None),
        productor=next((c.productor for c in crudos if c.productor), None),
        region=principal.region,
        fuentes=[
            Procedencia(fuente=c.fuente, id_externo=c.id_externo, url=c.url, visto=corridas.get(c.fuente, ahora))
            for c in crudos
        ],
        actualizado=ahora,
    )


def vigente(funcion: Funcion, ahora: datetime) -> bool:
    if funcion.sin_hora:
        return funcion.inicio.date() >= ahora.date()
    return funcion.inicio >= ahora - MARGEN_PASADO


# --- Proceso completo ----------------------------------------------------------------------------

def cargar_resultados(directorio: Path = DIR_FUENTES) -> list[ResultadoFuente]:
    return [
        ResultadoFuente.model_validate_json(archivo.read_text(encoding="utf-8"))
        for archivo in sorted(directorio.glob("*.json"))
    ]


def armar_cartelera(
    resultados: list[ResultadoFuente], alias: list[dict], ahora: datetime, geocodificar=None, buscar_genero=None,
) -> tuple[list[Evento], list[Lugar], list[Ciclo]]:
    crudos = [e for r in resultados for e in r.eventos]
    corridas = {r.fuente: r.corrida for r in resultados}
    catalogo = Catalogo(alias)
    lugar_de = [catalogo.asignar(c.lugar.nombre, c.lugar.direccion, c.lugar.lat, c.lugar.lon) for c in crudos]

    # Salas que ninguna fuente ubica: se buscan por dirección (o por nombre) en OpenStreetMap.
    if geocodificar:
        for lugar in catalogo.lugares.values():
            if lugar.lat is None and not re.search(r"confirmar|sin lugar|a definir|varios", lugar.nombre, re.I):
                # Un nombre de una sola palabra ("Sitio") es demasiado ambiguo para buscarlo sin dirección.
                por_nombre = len(lugar.nombre.split()) > 1
                punto = (geocodificar(lugar.direccion) if lugar.direccion else None) or (
                    geocodificar(lugar.nombre) if por_nombre else None
                )
                if punto:
                    lugar.lat, lugar.lon = punto

    # Sin coordenadas no se puede saber si es Montevideo: entra solo si la sala ya es conocida con ubicación.
    ubicables = [
        i for i, c in enumerate(crudos)
        if c.lugar.lat is not None or catalogo.lugares[lugar_de[i]].lat is not None
    ]
    if len(ubicables) < len(crudos):
        log.info("unificar: %s eventos descartados por no tener ubicación conocida", len(crudos) - len(ubicables))
    crudos = [crudos[i] for i in ubicables]
    lugar_de = [lugar_de[i] for i in ubicables]

    eventos = []
    for grupo in agrupar(crudos, lugar_de):
        evento = fusionar([crudos[i] for i in grupo], lugar_de[grupo[0]], corridas, ahora)
        evento.funciones = [f for f in evento.funciones if vigente(f, ahora)]
        if evento.funciones:
            eventos.append(evento)
    eventos.sort(key=lambda e: (e.funciones[0].inicio, e.titulo))

    usados = {e.lugar_id for e in eventos}
    lugares = sorted((l for l in catalogo.lugares.values() if l.id in usados), key=lambda l: l.nombre)
    ciclos = etiquetar(eventos, {l.id: l.nombre for l in lugares}, buscar_genero)
    return eventos, lugares, ciclos


def _escribir(nombre: str, clave: str, items: list, ahora: datetime) -> None:
    contenido = {"generado": ahora.isoformat(), "cantidad": len(items), clave: [i.model_dump(mode="json") for i in items]}
    (DIR_DATOS / nombre).write_text(json.dumps(contenido, ensure_ascii=False, indent=1), encoding="utf-8")


def unificar(ahora: datetime | None = None) -> list[Evento]:
    ahora = ahora or datetime.now(MONTEVIDEO)
    resultados = cargar_resultados()
    geocodificador, generos = Geocodificador(), BuscadorDeGeneros()
    eventos, lugares, ciclos = armar_cartelera(resultados, cargar_alias(), ahora, geocodificador, generos)
    geocodificador.guardar()
    generos.guardar()
    DIR_DATOS.mkdir(exist_ok=True)
    _escribir("eventos.json", "eventos", eventos, ahora)
    _escribir("lugares.json", "lugares", lugares, ahora)
    _escribir("ciclos.json", "ciclos", ciclos, ahora)
    crudos = sum(r.cantidad for r in resultados)
    log.info("unificar: %s eventos de %s fuentes (%s registros crudos), %s lugares, %s ciclos",
             len(eventos), len(resultados), crudos, len(lugares), len(ciclos))
    return eventos
