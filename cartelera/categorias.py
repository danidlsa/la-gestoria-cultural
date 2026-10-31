"""Clasificación por palabras clave, para fuentes que no informan la categoría."""

import re

from cartelera.geo import sin_tildes

# Palabras completas (con plural opcional) y algunas raíces marcadas con "*".
REGLAS: list[tuple[str, list[str]]] = [
    ("carnaval", ["murga", "carnaval", "parodistas", "humoristas", "revista", "lubolos", "candombe"]),
    ("infantil", ["infantil", "infantiles", "ninos", "ninas", "familia", "familiar", "chicos", "titeres", "princesa"]),
    ("danza", ["ballet", "danza", "bailarin*", "coreograf*", "flamenco"]),
    ("humor", ["stand up", "standup", "humor", "humorista", "monologo"]),
    ("musica", ["concierto", "recital", "orquesta", "filarmonica", "sinfonica", "banda", "cuarteto",
                "quinteto", "trio", "coro", "coral", "tango", "jazz", "rock", "cumbia", "piano",
                "guitarra", "tour", "gira", "en vivo", "live", "cantante", "album", "disco",
                "opera", "musical", "dj set"]),
    ("teatro", ["obra", "teatro", "teatral", "dramaturg*", "unipersonal", "comedia", "tragedia",
                "elenco", "puesta en escena", "actriz", "actor"]),
    ("cine", ["cine", "pelicula", "film", "proyeccion", "documental"]),
    ("exposicion", ["muestra", "exposicion", "exhibicion", "museo"]),
    ("charla", ["charla", "conferencia", "presentacion del libro", "seminario"]),
    ("fiesta", ["fiesta", "party", "dj", "after", "boliche"]),
]


def _patron(palabras: list[str]) -> re.Pattern:
    partes = [rf"{re.escape(p[:-1])}\w*" if p.endswith("*") else rf"{re.escape(p)}(?:e?s)?" for p in palabras]
    return re.compile(rf"\b(?:{'|'.join(partes)})\b")


_COMPILADAS = [(categoria, _patron(palabras)) for categoria, palabras in REGLAS]

DEPORTE = re.compile(
    r"\bvs\.?\b|\b(futbol|basquet|basketball|baloncesto|rugby|voley|handball|tenis|boxeo|"
    r"mma|ufc|maraton|carrera|campeonato|liga|torneo|clasico|globetrotters)\b"
)


def clasificar(*textos: str | None, por_defecto: str = "otros") -> str:
    """Devuelve la primera categoría cuyas palabras clave aparecen en el texto."""
    plano = sin_tildes(" ".join(t for t in textos if t))
    for categoria, patron in _COMPILADAS:
        if patron.search(plano):
            return categoria
    return por_defecto


def es_deporte(*textos: str | None) -> bool:
    return bool(DEPORTE.search(sin_tildes(" ".join(t for t in textos if t))))


_POR_LUGAR = [
    ("cine", re.compile(r"\b(cine|cinemateca|cines)\b")),
    ("exposicion", re.compile(r"\b(museo|galeria)\b")),
    ("teatro", re.compile(r"\b(teatro|sala)\b")),
]


def categoria_por_lugar(nombre_lugar: str | None) -> str:
    """Respaldo cuando el texto del evento no alcanza: el tipo de sala."""
    plano = sin_tildes(nombre_lugar or "")
    for categoria, patron in _POR_LUGAR:
        if patron.search(plano):
            return categoria
    return "otros"


_CANCELADO = re.compile(r"\b(cancelad[oa]s?|suspendid[oa]s?)\b")


def esta_cancelado(titulo: str | None) -> bool:
    return bool(_CANCELADO.search(sin_tildes(titulo or "")))
