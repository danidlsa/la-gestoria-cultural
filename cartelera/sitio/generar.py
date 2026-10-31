"""Genera la web estática a partir de los JSON de datos/.

Todo lo que se puede calcular de antemano (textos, rangos de precio, conteos) se calcula acá, en
Python. El JavaScript del navegador solo filtra, dibuja el calendario y el mapa.
"""

import html
import json
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from cartelera.geo import VARIOS_BARRIOS

DIR_DATOS = Path("datos")
SALIDA = Path("sitio_generado")
AQUI = Path(__file__).parent
# El texto de la pestaña "¿Qué es La Gestoría?". Se edita en Markdown.
QUE_ES = Path("docs/que-es-la-gestoria.md")

NOMBRE_SITIO = "La Gestoría Cultural"
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
CATEGORIAS = {
    "musica": "Música", "teatro": "Teatro", "danza": "Danza", "humor": "Humor", "cine": "Cine",
    "exposicion": "Exposiciones", "infantil": "Infantil", "fiesta": "Fiestas", "festival": "Festivales",
    "carnaval": "Carnaval", "tour": "Recorridos", "charla": "Charlas", "taller": "Talleres y cursos", "otros": "Otros",
}
# Subrubros que se ofrecen al elegir un rubro, aunque todavía no haya eventos (llegan con nuevas fuentes).
SUBCATEGORIAS = {
    "teatro": {"comedia_nacional": "Comedia Nacional"},
    "danza": {"ballet_sodre": "Ballet Nacional del Sodre"},
    "humor": {"stand_up": "Stand up"},
    "cine": {"cinemateca": "Cinemateca"},
    # Géneros gruesos: el resto de la música queda en "Otros".
    "musica": {"clasica": "Clásica y lírica", "tropical": "Tropical", "rock_pop": "Rock y pop"},
}
# Presupuesto según el precio "desde" (en pesos uruguayos).
PRESUPUESTOS = [
    ("gratis", "Gratis", ""),
    ("ganga", "Ganga", "menos de $500"),
    ("accesible", "Accesible", "$500 a $999"),
    ("normal", "Normal", "$1.000 a $1.600"),
    ("carito", "Carito", "más de $1.600"),
]
FUENTES = {
    "tickantel": "Tickantel", "redtickets": "RedTickets", "sodre": "el Sodre", "cinemateca": "Cinemateca",
    "cartelera_mvd": "la Cartelera de Montevideo Portal", "solis": "el Teatro Solís",
    "teatro_de_verano": "el Teatro de Verano", "galpon": "El Galpón", "abitab": "Abitab",
    "portal_im": "el portal de eventos de la Intendencia", "zitarrosa": "la Sala Zitarrosa",
    "ticketmaster_uy": "Ticketmaster",
}
# Para los botones de compra: dónde se consigue la entrada.
VIAS = {
    "cartelera_mvd": "la Cartelera", "solis": "el Solís", "teatro_de_verano": "el Teatro de Verano", "sodre": "el Sodre",
    "portal_im": "la Intendencia", "zitarrosa": "la Zitarrosa",
}


def fecha_corta(inicio: str, sin_hora: bool = False) -> str:
    """'2026-10-30T17:30:00-03:00' -> 'vie 30 oct · 17:30'."""
    momento = datetime.fromisoformat(inicio)
    texto = f"{DIAS[momento.weekday()]} {momento.day} {MESES[momento.month - 1]}"
    return texto if sin_hora else f"{texto} · {momento:%H:%M}"


def presupuesto(precio: dict | None) -> str | None:
    if not precio:
        return None
    if precio.get("gratis") or (precio.get("desde") == 0 and not precio.get("hasta")):
        return "gratis"
    desde = precio.get("desde")
    if desde is None:
        return None
    if desde < 500:
        return "ganga"
    if desde < 1000:
        return "accesible"
    if desde <= 1600:
        return "normal"
    return "carito"


def precio_texto(precio: dict | None) -> str | None:
    if not precio:
        return None
    if presupuesto(precio) == "gratis":
        return "Gratis"
    desde, hasta = precio.get("desde"), precio.get("hasta")
    if desde is None:
        return None
    pesos = lambda valor: f"${valor:,.0f}".replace(",", ".")  # noqa: E731
    return f"{pesos(desde)} a {pesos(hasta)}" if hasta and hasta != desde else pesos(desde)


def _leer(nombre: str, clave: str) -> tuple[list[dict], str]:
    ruta = DIR_DATOS / nombre
    if not ruta.exists():
        return [], ""
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    return contenido[clave], contenido["generado"]


def en_cartel(evento: dict) -> bool:
    """Temporadas y muestras: muchas fechas a lo largo de varias semanas.

    En el calendario van aparte ("También en cartel") para que no tapen lo que pasa solo ese día.
    """
    dias = sorted({f["inicio"][:10] for f in evento["funciones"]})
    duracion = (datetime.fromisoformat(dias[-1]) - datetime.fromisoformat(dias[0])).days
    return len(dias) >= 6 and duracion >= 14


def datos_para_el_navegador(eventos: list[dict], lugares: dict[str, dict], ciclos: list[dict]) -> dict:
    """Versión compacta de los eventos para filtrar en el navegador."""
    return {
        "eventos": [
            {
                "id": e["id"],
                "titulo": e["titulo"],
                "url": (e.get("entradas") or e["fuentes"])[0]["url"],
                "precioTexto": precio_texto(e.get("precio")),
                "categoria": e["categoria"],
                "enCartel": en_cartel(e),
                "sub": e.get("subcategoria"),
                "etiquetas": e.get("etiquetas", []),
                "ciclo": e.get("ciclo_id"),
                "lugar": e["lugar_id"],
                "presupuesto": presupuesto(e.get("precio")),
                "promos": [b["programa"] for b in e.get("beneficios", [])],
                "funciones": [[f["inicio"], f.get("sin_hora", False), f.get("fin")] for f in e["funciones"]],
                "texto": " ".join(filter(None, [e["titulo"], lugares.get(e["lugar_id"], {}).get("nombre"), e.get("productor")])),
            }
            for e in eventos
        ],
        "lugares": {
            id_: {"nombre": l["nombre"], "lat": l.get("lat"), "lon": l.get("lon"), "direccion": l.get("direccion")}
            for id_, l in lugares.items()
        },
        "ciclos": {c["id"]: c["titulo"] for c in ciclos},
        "categorias": CATEGORIAS,
        "subcategorias": SUBCATEGORIAS,
    }


def _en_linea(texto: str) -> str:
    """Enlaces y negritas de Markdown, con el resto del texto escapado. Solo enlaces web, mail o internos."""
    texto = html.escape(texto, quote=False)
    texto = re.sub(r"\[([^\]]+)\]\(((?:https?://|mailto:)[^)\s]+|[\w./#-][^)\s:]*)\)",
                   lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', texto)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", texto)


def markdown_simple(texto: str) -> Markup:
    """Lo poco de Markdown que usa el texto de la pestaña: párrafos, listas, títulos, enlaces y negritas.
    Un salto de línea simple se respeta (la firma, por ejemplo)."""
    bloques = []
    for bloque in re.split(r"\n\s*\n", texto.strip()):
        lineas = [l.rstrip() for l in bloque.splitlines()]
        if all(l.startswith("- ") for l in lineas):
            items = "".join(f"<li>{_en_linea(l[2:])}</li>" for l in lineas)
            bloques.append(f"<ul>{items}</ul>")
        elif titulo := re.match(r"(#{1,3})\s+(.*)", bloque):
            nivel = len(titulo.group(1)) + 1
            bloques.append(f"<h{nivel}>{_en_linea(titulo.group(2))}</h{nivel}>")
        else:
            bloques.append(f"<p>{'<br>'.join(_en_linea(l) for l in lineas)}</p>")
    return Markup("\n".join(bloques))


def generar() -> Path:
    eventos, generado = _leer("eventos.json", "eventos")
    lugares_lista, _ = _leer("lugares.json", "lugares")
    ciclos, _ = _leer("ciclos.json", "ciclos")
    lugares = {l["id"]: l for l in lugares_lista}

    entorno = Environment(loader=FileSystemLoader(AQUI / "plantillas"), autoescape=select_autoescape(["html", "j2"]))
    entorno.filters["fecha_corta"] = fecha_corta
    entorno.filters["precio_texto"] = precio_texto
    entorno.filters["presupuesto"] = presupuesto

    por_categoria = Counter(e["categoria"] for e in eventos)
    por_lugar = Counter(e["lugar_id"] for e in eventos)
    promos = Counter(b["programa"] for e in eventos for b in e.get("beneficios", []))
    datos = datos_para_el_navegador(eventos, lugares, ciclos)

    pagina = entorno.get_template("index.html.j2").render(
        sitio=NOMBRE_SITIO,
        eventos=eventos,
        lugares=lugares,
        ciclos={c["id"]: c for c in ciclos},
        # "Festivales" va como etiqueta aparte (incluye festivales de cualquier rubro).
        categorias=[(k, v, por_categoria[k]) for k, v in CATEGORIAS.items() if por_categoria[k] and k != "festival"],
        nombres_categoria=CATEGORIAS,
        varios_barrios=VARIOS_BARRIOS,
        nombres_subcategoria={clave: nombre for opciones in SUBCATEGORIAS.values() for clave, nombre in opciones.items()},
        presupuestos=PRESUPUESTOS,
        salas=sorted(((l["id"], l["nombre"], por_lugar[l["id"]]) for l in lugares_lista), key=lambda s: s[1].lower()),
        promos=promos.most_common(),
        fuentes={**FUENTES, **VIAS},
        nombres_fuentes=[FUENTES[f] for f in sorted({p["fuente"] for e in eventos for p in e["fuentes"]}) if f in FUENTES],
        generado=fecha_corta(generado) if generado else "",
        cantidad_gratis=sum(1 for e in eventos if presupuesto(e.get("precio")) == "gratis"),
        cantidad_promos=sum(1 for e in eventos if e.get("beneficios")),
        # Un "<" en los datos podría cerrar el <script> donde van embebidos: va escapado (JSON lo lee igual).
        datos_json=json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c"),
    )

    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    shutil.copytree(AQUI / "estaticos", SALIDA)
    (SALIDA / "index.html").write_text(pagina, encoding="utf-8")
    if QUE_ES.exists():
        que_es = entorno.get_template("que-es.html.j2").render(
            sitio=NOMBRE_SITIO, contenido=markdown_simple(QUE_ES.read_text(encoding="utf-8")),
        )
        (SALIDA / "que-es.html").write_text(que_es, encoding="utf-8")
    # Los datos también quedan publicados, por si alguien quiere usarlos.
    for nombre in ("eventos.json", "lugares.json", "ciclos.json"):
        if (DIR_DATOS / nombre).exists():
            shutil.copy(DIR_DATOS / nombre, SALIDA / nombre)
    return SALIDA / "index.html"
