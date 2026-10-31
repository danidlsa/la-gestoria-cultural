"""Género grueso de la música cuando el texto del evento no lo dice: se busca al artista en Wikidata.

Muchos títulos son solo el nombre del artista ("CREMA", "Dyango", "ERUCA SATIVA"). Wikidata es
abierta, gratis y sin API key, y para músicos y bandas tiene la propiedad "género" (P136). Spotify
dejó de informar géneros en febrero de 2026 y MusicBrainz casi no tiene artistas locales.

Se acepta un resultado solo si es una persona o un grupo musical con género y su nombre coincide
con el buscado. Igual puede haber homónimos (dos bandas que se llaman igual): para eso está
`config/generos.toml`, con correcciones por artista. Cada nombre se consulta una sola vez; los que
no se encuentran se reintentan después de un mes.

No usa `cartelera.http.Cliente` (que aplica robots.txt, pensado para rastreadores): el uso de la API
lo regula la política de Wikimedia, que pide un User-Agent con contacto y pedidos de a uno.
"""

import json
import logging
import re
import time
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from rapidfuzz import fuzz

from cartelera.geo import sin_tildes
from cartelera.http import USER_AGENT

API = "https://www.wikidata.org/w/api.php"
CACHE = Path("datos/cache/generos_wikidata.json")
CORRECCIONES = Path("config/generos.toml")
MAX_CONSULTAS = 80  # nombres nuevos por corrida
REINTENTAR_FALLIDAS = timedelta(days=30)
PAUSA = 0.3

# Qué es la entidad: persona o algún tipo de grupo musical.
PERSONA = "Q5"
GRUPOS = {"Q215380", "Q5741069", "Q2088357", "Q9212979", "Q281643", "Q641066", "Q56816954"}
PAISES_CERCANOS = {"Q77", "Q414"}  # Uruguay y Argentina: desempatan homónimos

# Etiquetas de género de Wikidata (en español o inglés) -> género grueso.
_GENERO_DE_ETIQUETA = [
    ("clasica", re.compile(r"clasic|classical|opera|barroc|baroque|sinfon|symphon|chamber|camara|lirica|choral|coral|romantic")),
    ("tropical", re.compile(r"cumbia|salsa|plena|merengue|bachata|cuarteto|reggaeton|tropical")),
    ("rock_pop", re.compile(r"rock|pop|punk|metal|indie|grunge|hip hop|hip-hop|rap|trap|alternativ|new wave|emo|ska|hardcore")),
]
# Palabras de los títulos que no son parte del nombre del artista.
_RUIDO = re.compile(
    r"\s*(\ben vivo\b|\ben concierto\b|\bpresentan?\b.*|\bgira\b.*|\btour\b.*|\(.*?\)|\d{1,2}/\d{1,2}.*)", re.I,
)
_SEPARADORES = re.compile(r"\s+[-–|/]\s+|[:.]\s+")
_NO_ES_ARTISTA = re.compile(
    r"\b(festival|fest|aniversario|premios?|concurso|show|fiesta|noche de|jam|milonga|ciclo|edicion|muestra|"
    r"temporada|encuentro|homenaje|tributo|podcast|lanzamiento)\b"
)
log = logging.getLogger(__name__)


def _clave(nombre: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", sin_tildes(nombre))).strip()


def artistas_probables(titulo: str) -> list[str]:
    """Nombres de artista que podría haber en un título, del más probable al menos.

    'Marty Friedman en MMBOX - 15/11' -> ['Marty Friedman en MMBOX', 'Marty Friedman']
    'TRIBUTO A OASIS SUPERNOVA' -> ['OASIS SUPERNOVA', 'OASIS']
    """
    homenaje = re.search(r"\b(?:tributo|homenaje) a\s+(.+)", titulo, re.I)
    base = homenaje.group(1) if homenaje else _SEPARADORES.split(titulo)[0]
    base = _RUIDO.sub("", base).strip(" .,'\"«»“”")
    if not homenaje and _NO_ES_ARTISTA.search(sin_tildes(base)):
        return []
    candidatos = [base]
    for corte in (r"\s+en\s+", r"\s+(?:y|&|\+)\s+|,\s*", r"\s+"):
        primero = re.split(corte, base, maxsplit=1, flags=re.I)[0]
        # Cortar por espacio solo sirve para tributos con un apodo detrás ("OASIS SUPERNOVA").
        if corte == r"\s+" and not homenaje:
            continue
        candidatos.append(primero)
    return [c for c in dict.fromkeys(c.strip() for c in candidatos) if 3 <= len(c) <= 60 and len(c.split()) <= 6]


def genero_de_etiquetas(etiquetas: list[str]) -> str | None:
    """El género grueso más votado entre los géneros de un artista (desempata el orden de Wikidata)."""
    votos: dict[str, int] = {}
    for etiqueta in etiquetas:
        plano = sin_tildes(etiqueta)
        for genero, patron in _GENERO_DE_ETIQUETA:
            if patron.search(plano):
                votos[genero] = votos.get(genero, 0) + 1
                break
    return max(votos, key=votos.get) if votos else None


def cargar_correcciones() -> dict[str, str | None]:
    """{nombre normalizado: género}; un género vacío quiere decir "no clasificar"."""
    if not CORRECCIONES.exists():
        return {}
    datos = tomllib.loads(CORRECCIONES.read_text(encoding="utf-8"))
    return {_clave(nombre): genero or None for nombre, genero in datos.get("artistas", {}).items()}


class BuscadorDeGeneros:
    def __init__(self, correcciones: dict[str, str | None] | None = None):
        self._correcciones = cargar_correcciones() if correcciones is None else correcciones
        self._http: httpx.Client | None = None
        self._consultas = 0
        try:
            self._cache = json.loads(CACHE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self._cache = {}
        self._cache.setdefault("artistas", {})
        self._cache.setdefault("generos", {})

    def __call__(self, titulo: str) -> str | None:
        for nombre in artistas_probables(titulo):
            clave = _clave(nombre)
            if clave in self._correcciones:
                return self._correcciones[clave]
            etiquetas = self._etiquetas_de(nombre, clave)
            if etiquetas:
                return genero_de_etiquetas(etiquetas)
        return None

    def _etiquetas_de(self, nombre: str, clave: str) -> list[str] | None:
        guardado = self._cache["artistas"].get(clave)
        vigente = guardado and (guardado["generos"] or datetime.now() - datetime.fromisoformat(guardado["fecha"]) < REINTENTAR_FALLIDAS)
        if not vigente:
            if self._consultas >= MAX_CONSULTAS:
                return None
            self._consultas += 1
            try:
                entidad, generos = self._buscar(nombre)
            except Exception as error:  # noqa: BLE001 - sin Wikidata el evento queda sin género, nada más
                log.warning("wikidata %r: %s", nombre, error)
                return None
            guardado = {"id": entidad, "generos": generos, "fecha": datetime.now().isoformat()}
            self._cache["artistas"][clave] = guardado
        return [self._cache["generos"].get(g, "") for g in guardado["generos"]] or None

    def _pedir(self, **parametros) -> dict:
        self._http = self._http or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=20)
        time.sleep(PAUSA)
        respuesta = self._http.get(API, params={"format": "json", **parametros})
        respuesta.raise_for_status()
        return respuesta.json()

    def _buscar(self, nombre: str) -> tuple[str | None, list[str]]:
        """(id de Wikidata, ids de sus géneros) del músico o grupo que se llama así, o (None, [])."""
        resultados = self._pedir(action="wbsearchentities", search=nombre, language="es", uselang="es", limit=7)
        parecidos = [
            r["id"] for r in resultados.get("search", [])
            if fuzz.ratio(_clave(r.get("match", {}).get("text") or r.get("label", "")), _clave(nombre)) >= 90
        ]
        if not parecidos:
            return None, []
        entidades = self._pedir(action="wbgetentities", ids="|".join(parecidos), props="claims")["entities"]
        candidatos = []
        for orden, ident in enumerate(parecidos):
            reclamos = entidades.get(ident, {}).get("claims", {})
            tipos = set(_valores(reclamos, "P31"))
            generos = _valores(reclamos, "P136")
            es_musico = bool(tipos & GRUPOS) or (PERSONA in tipos and "P106" in reclamos)
            if generos and es_musico:
                cercano = bool(set(_valores(reclamos, "P27") + _valores(reclamos, "P495")) & PAISES_CERCANOS)
                candidatos.append((not cercano, orden, ident, generos[:6]))
        if not candidatos:
            return None, []
        _, _, ident, generos = min(candidatos)
        faltan = [g for g in generos if g not in self._cache["generos"]]
        if faltan:
            for gid, datos in self._pedir(action="wbgetentities", ids="|".join(faltan), props="labels", languages="es|en")["entities"].items():
                etiquetas = datos.get("labels", {})
                self._cache["generos"][gid] = (etiquetas.get("es") or etiquetas.get("en") or {}).get("value", "")
        return ident, generos

    def guardar(self) -> None:
        if self._http:
            self._http.close()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(self._cache, ensure_ascii=False, indent=0), encoding="utf-8")


def _valores(reclamos: dict, propiedad: str) -> list[str]:
    return [
        r["mainsnak"]["datavalue"]["value"]["id"]
        for r in reclamos.get(propiedad, [])
        if r.get("mainsnak", {}).get("datavalue", {}).get("type") == "wikibase-entityid"
    ]
