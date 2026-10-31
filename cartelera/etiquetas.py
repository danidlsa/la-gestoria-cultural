"""Subcategorías, etiquetas y ciclos: lo que arma las secciones especiales de la web."""

import re
from collections import defaultdict

from cartelera.geo import sin_tildes
from cartelera.modelo import Ciclo, Evento

# (subcategoría, categoría a la que pertenece, patrón sobre título + descripción + productor + lugar)
SUBCATEGORIAS = [
    ("comedia_nacional", "teatro", re.compile(r"\bcomedia nacional\b")),
    ("ballet_sodre", "danza", re.compile(r"\b(bns|ballet nacional( del sodre)?)\b")),
    ("stand_up", "humor", re.compile(r"\b(stand ?up|monologo|comedia de stand)\b")),
    ("cinemateca", "cine", re.compile(r"\bcinemateca\b")),
]
# Géneros gruesos de la música. Si un texto nombra más de uno, gana el que aparece primero.
GENEROS_MUSICA = [
    ("clasica", re.compile(
        r"\b(orquesta (de camara|juvenil)|filarmonica|sinfonic\w*|ossodre|opera|lirica|zarzuela|musica de camara|"
        r"cuarteto de (cuerdas|vientos)|quinteto de vientos|quartet|sonatas?|conciertos? para|recital de piano|"
        r"violonchel\w*|clavecin|barroc\w*|baroque|choir|soprano|baritono|requiem|musica clasica|"
        r"bach|beethoven|mozart|chopin|vivaldi|brahms|schubert|tchaikovsky|chaikovski|monteverdi|haendel|handel)\b"
    )),
    ("tropical", re.compile(
        r"\b(cumbia\w*|plena uruguaya|salsa|bachata|merengue|cuarteto cordobes|cuartetazo|reggaeton|regueton|tropical\w*|"
        r"movida tropical)\b"
    )),
    ("rock_pop", re.compile(
        r"\b(rock\w*|pop|punk\w*|metal\w*|heavy|grunge|indie|hardcore|stoner|emo|ska|hip ?hop|rap|trap|"
        r"k-?pop|britpop|new wave)\b"
    )),
]
FESTIVAL = re.compile(r"\b(festival|fest)\b")
# "Ciclo de piano Raquel Boldorini", "Ciclo Marea - Lucía Chappe", "Ciclo de Música de Cámara 1-11"
CICLO_EXPLICITO = re.compile(r"^(ciclo\b[^:\-–|0-9]*)", re.I)
# "Partículas: Miel + Malapraxxis": un prefijo antes de ":" que se repite en la misma sala
PREFIJO = re.compile(r"^([^:]{3,40}):\s+\S")


def subcategoria(evento: Evento, lugar_nombre: str = "") -> str | None:
    texto = sin_tildes(" ".join(filter(None, [evento.titulo, evento.descripcion_corta, evento.productor, lugar_nombre])))
    for nombre, categoria, patron in SUBCATEGORIAS:
        if patron.search(texto):
            # Stand up define la categoría (a veces llega como teatro o charla); el resto solo la refina.
            if nombre == "stand_up" or evento.categoria == categoria:
                return nombre
    return None


def genero_por_texto(evento: Evento) -> str | None:
    """Género grueso de un evento de música según sus palabras: primero el título, después el resto.
    "Una mezcla única de rock, cumbia y ritmos latinos" es rock: gana lo que se nombra primero."""
    for texto in (evento.titulo, " ".join(filter(None, [evento.descripcion_corta, evento.productor]))):
        plano = sin_tildes(texto)
        encontrados = [(m.start(), genero) for genero, patron in GENEROS_MUSICA if (m := patron.search(plano))]
        if encontrados:
            return min(encontrados)[1]
    return None


def etiquetas(evento: Evento) -> list[str]:
    es_festival = evento.categoria == "festival" or FESTIVAL.search(sin_tildes(evento.titulo))
    return ["festival"] if es_festival else []


def _slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes(texto)).strip("-")


def detectar_ciclos(eventos: list[Evento]) -> list[Ciclo]:
    """Asigna `ciclo_id` a los eventos que forman parte de un ciclo y devuelve los ciclos."""
    candidatos: dict[tuple[str, str], list[Evento]] = defaultdict(list)
    nombres: dict[str, str] = {}
    for evento in eventos:
        if evento.ciclo_nombre:
            clave = _slug(evento.ciclo_nombre)
            nombres[clave] = evento.ciclo_nombre
            candidatos[(clave, "")].append(evento)
            continue
        explicito = CICLO_EXPLICITO.match(evento.titulo)
        if explicito:
            nombre = explicito.group(1).strip(" -–")
            candidatos[(_slug(nombre), "")].append(evento)
            continue
        prefijo = PREFIJO.match(evento.titulo)
        if prefijo:
            candidatos[(_slug(prefijo.group(1)), evento.lugar_id)].append(evento)

    ciclos = []
    for (clave, lugar_id), miembros in candidatos.items():
        explicito = lugar_id == ""
        # Un prefijo cualquiera es ciclo solo si se repite; "Ciclo …" alcanza con un evento.
        if not explicito and len(miembros) < 2:
            continue
        if clave in nombres:
            titulo = nombres[clave]
        else:
            titulo = (CICLO_EXPLICITO.match(miembros[0].titulo) or PREFIJO.match(miembros[0].titulo)).group(1).strip(" -–")
        ciclo_id = f"ciclo-{clave}"
        for evento in miembros:
            evento.ciclo_id = ciclo_id
        inicios = [f.inicio for e in miembros for f in e.funciones]
        lugares = {e.lugar_id for e in miembros}
        ciclos.append(Ciclo(
            id=ciclo_id, titulo=titulo[:1].upper() + titulo[1:],
            lugar_id=lugares.pop() if len(lugares) == 1 else None,
            desde=min(inicios), hasta=max(inicios), cantidad=len(miembros),
        ))
    return sorted(ciclos, key=lambda c: c.desde)


def etiquetar(eventos: list[Evento], nombres_lugar: dict[str, str], buscar_genero=None) -> list[Ciclo]:
    """`buscar_genero(titulo)` es el respaldo para la música que no se clasifica por palabras (Wikidata)."""
    for evento in eventos:
        evento.subcategoria = subcategoria(evento, nombres_lugar.get(evento.lugar_id, ""))
        if evento.subcategoria == "stand_up":
            evento.categoria = "humor"
        if evento.categoria == "musica" and not evento.subcategoria:
            evento.subcategoria = genero_por_texto(evento) or (buscar_genero(evento.titulo) if buscar_genero else None)
        evento.etiquetas = etiquetas(evento)
    return detectar_ciclos(eventos)
