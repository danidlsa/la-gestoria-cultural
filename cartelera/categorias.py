"""Clasificación por palabras clave, para fuentes que no informan la categoría."""

import re

from cartelera.geo import sin_tildes

# Palabras completas (con plural opcional) y algunas raíces marcadas con "*".
REGLAS: list[tuple[str, list[str]]] = [
    # "revista" no: casi siempre es una revista de papel ("fue directora de la revista ARTE"); las de carnaval igual
    # dicen "carnaval".
    ("carnaval", ["murga", "carnaval", "parodistas", "humoristas", "lubolos", "candombe"]),
    # "familia" sola no: "historias de amor, familia y barro" son crónicas para grandes. Sí "para toda la familia".
    ("infantil", ["infantil", "infantiles", "ninos", "ninas", "en familia", "toda la familia", "para la familia",
                  "para las familias", "espectaculo familiar", "funcion familiar", "show familiar", "actividad familiar",
                  "propuesta familiar", "chicos", "titeres", "princesa"]),
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


# Lo que se decide por el título, antes que el texto largo: un taller o una feria lo dicen en el nombre ("Laboratorio
# de escritura", "Feria Bohemia"), y la descripción suele hablar de todo ("espectáculos en vivo", "fue directora de una
# revista"). En el texto no se buscan: "el elenco del taller de teatro" presenta una obra.
_POR_TITULO = [
    ("feria", re.compile(r"\b(ferias?|mercadillos?)\b")),
    ("taller", re.compile(r"\b(taller(es)?|cursos?|workshops?|laboratorios?|clases?\s+abiertas?|seminario\s+taller)\b")),
]


def por_titulo(titulo: str | None) -> str | None:
    """La categoría que dice el título por sí solo (taller, feria), o None."""
    plano = sin_tildes(titulo or "")
    return next((categoria for categoria, patron in _POR_TITULO if patron.search(plano)), None)


# Lo que parece de una categoría y es de otra: la "ópera prima" de un director es su primera película.
_ENGANOSAS = re.compile(r"\bopera\s+prima\b")


def clasificar(*textos: str | None, por_defecto: str = "otros") -> str:
    """Devuelve la categoría que dice el título (el primer texto), o la primera cuyas palabras clave aparecen."""
    if categoria := por_titulo(textos[0] if textos else None):
        return categoria
    plano = _ENGANOSAS.sub(" pelicula ", sin_tildes(" ".join(t for t in textos if t)))
    for categoria, patron in _COMPILADAS:
        if patron.search(plano):
            return categoria
    return por_defecto


# Una comida (la cena de Nochebuena de un hotel, un almuerzo buffet) no es un evento cultural, aunque la ticketera la
# ponga en "Fiestas"; salvo que sea un show con cena ("Cena show de tango").
_COMIDA = re.compile(r"^(?:cena|almuerzo|brunch|desayuno|buffet|men[uú])\b|\b(?:almuerzo|brunch)\s+buffet\b")
_CON_SHOW = re.compile(r"\bshow\b|concierto|espectaculo|en vivo|tango|musica|recital|stand ?up|humor|teatro|baile|dj\b")


def es_comida(titulo: str | None) -> bool:
    plano = sin_tildes(titulo or "")
    return bool(_COMIDA.search(plano)) and not _CON_SHOW.search(plano)


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
