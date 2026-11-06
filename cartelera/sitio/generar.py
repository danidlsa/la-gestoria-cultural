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

from cartelera import especiales
from cartelera.geo import VARIOS_BARRIOS
from cartelera.scrapers.base import MONTEVIDEO
from cartelera.scrapers.propuestos import configuracion as configuracion_agrega

DIR_DATOS = Path("datos")
SALIDA = Path("sitio_generado")
AQUI = Path(__file__).parent
# El texto de la pestaña "¿Qué es La Gestoría?". Se edita en Markdown.
QUE_ES = Path("docs/que-es-la-gestoria.md")

NOMBRE_SITIO = "La Gestoría Cultural"
# La dirección pública del sitio: para la vista previa al compartir, el sitemap y la dirección oficial (canonical).
URL_SITIO = "https://lagestoriacultural.uy/"
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
CATEGORIAS = {
    "musica": "Música", "teatro": "Teatro", "danza": "Danza", "humor": "Humor", "cine": "Cine",
    "exposicion": "Exposiciones", "infantil": "Infantil", "fiesta": "Fiestas", "festival": "Festivales",
    "carnaval": "Carnaval", "tour": "Recorridos y tours", "charla": "Charlas", "taller": "Talleres y cursos", "otros": "Otros",
}
# Subrubros que se ofrecen al elegir un rubro, aunque todavía no haya eventos (llegan con nuevas fuentes).
SUBCATEGORIAS = {
    "teatro": {"comedia_nacional": "Comedia Nacional"},
    "danza": {"ballet_sodre": "Ballet Nacional del Sodre"},
    "humor": {"stand_up": "Stand up"},
    "cine": {"cinemateca": "Cinemateca"},
    # Géneros gruesos: el rock, el pop y lo que no se pudo clasificar van juntos en el botón de "otros".
    "musica": {"clasica": "Clásica y lírica", "tropical": "Tropical"},
}
# Nombre del botón "Otros" de cada rubro, si no es "Otros".
SUBCATEGORIAS_OTROS = {"musica": "Rock, pop y otros"}
# Rubros cuyos subrubros se adivinan (y pueden fallar): llevan una nota de "experimental".
SUBCATEGORIAS_EXPERIMENTALES = ["musica"]
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
    "ticketmaster_uy": "Ticketmaster", "sala_del_museo": "la Sala del Museo", "gaucho": "Gaucho",
    "piano_piano": "Piano Piano", "ladiaria": "los beneficios de la diaria", "fever": "Fever",
    "museos_im": "los museos de la Intendencia", "mnav": "el Museo Nacional de Artes Visuales",
    "torres_garcia": "el Museo Torres García", "gurvich": "el Museo Gurvich", "mapi": "el MAPI",
    "mec_museos": "el calendario del Ministerio de Educación y Cultura",
    "salacamacua": "la Sala Camacuá", "mientrada": "MiEntrada", "cobraticket": "CobraTicket",
    "corchea": "la cartelera de Corchea", "propuestos": "los organizadores que mandan sus eventos",
}
# Para los botones de compra: dónde se consigue la entrada.
VIAS = {
    "cartelera_mvd": "la Cartelera", "solis": "el Solís", "teatro_de_verano": "el Teatro de Verano", "sodre": "el Sodre",
    "portal_im": "la Intendencia", "zitarrosa": "la Zitarrosa", "sala_del_museo": "la Sala del Museo",
    "antel_arena": "el Antel Arena", "ladiaria": "la diaria",
    "museos_im": "el museo", "mnav": "el MNAV", "torres_garcia": "el Museo Torres García",
    "gurvich": "el Museo Gurvich", "mapi": "el MAPI", "mec_museos": "el MEC",
    "salacamacua": "la Sala Camacuá", "corchea": "Corchea", "passline": "Passline", "entradasfans": "Entradas Fans",
    "instagram": "Instagram", "propuestos": "su web",
}
# Vías que son la ficha del evento, no una venta: el botón dice "Ver en …" y no "Entradas en …".
SOLO_INFORMACION = {
    "cartelera_mvd", "solis", "teatro_de_verano", "sodre", "galpon", "cinemateca", "portal_im", "zitarrosa",
    "sala_del_museo", "gaucho", "piano_piano", "ladiaria", "museos_im", "mnav", "torres_garcia",
    "gurvich", "mapi", "mec_museos", "salacamacua", "corchea", "instagram", "propuestos",
}


# Nunca se enlaza a la Cartelera de Montevideo Portal: es otra cartelera, no donde se compra ni la sala.
NUNCA_ENLAZAR = {"cartelera_mvd"}
# Programas de promos genéricos: van después de los que nombran a alguien (la diaria, un banco, un club).
PROMOS_GENERICAS = ("2x1 para todos", "Promo grupal", "Otras promos")
PROMOS_VISIBLES = 2


def entrada_principal(evento: dict) -> dict | None:
    """El único enlace de la tarjeta: una ticketera si hay; si no, la página de la sala o del organizador."""
    entradas = [e for e in evento.get("entradas", []) if e["via"] not in NUNCA_ENLAZAR]
    venta = [e for e in entradas if e["via"] not in SOLO_INFORMACION]
    if venta or entradas:
        return (venta or entradas)[0]
    fuente = next((f for f in evento["fuentes"] if f.get("fuente") not in NUNCA_ENLAZAR), None)
    return {"url": fuente["url"], "via": fuente.get("fuente", "")} if fuente else None


def promos_ordenadas(evento: dict) -> list[dict]:
    """Las promos de una tarjeta, primero las de programas con nombre."""
    return sorted(evento.get("beneficios", []), key=lambda b: b["programa"] in PROMOS_GENERICAS)


def fecha_corta(inicio: str, sin_hora: bool = False) -> str:
    """'2026-10-30T17:30:00-03:00' -> 'vie 30 oct · 17:30'."""
    momento = datetime.fromisoformat(inicio)
    texto = f"{DIAS[momento.weekday()]} {momento.day} {MESES[momento.month - 1]}"
    return texto if sin_hora else f"{texto} · {momento:%H:%M}"


def periodo_muestra(evento: dict) -> str:
    """'Hasta el 28 feb 2027', 'Desde el 28 nov · hasta el 4 abr 2027' o 'En exhibición' (sin fecha de cierre)."""
    def fecha(texto: str, con_anio: bool = True) -> str:
        dia = datetime.fromisoformat(texto[:10])
        return f"{dia.day} {MESES[dia.month - 1]}" + (f" {dia.year}" if con_anio else "")
    hoy = datetime.now().date().isoformat()
    inicio = evento["funciones"][0]["inicio"][:10] if evento.get("funciones") else hoy
    hasta = evento.get("hasta")
    if inicio > hoy:
        return f"Desde el {fecha(inicio, False)}" + (f" · hasta el {fecha(hasta)}" if hasta else "")
    return f"Hasta el {fecha(hasta)}" if hasta else "En exhibición"


def especiales_para_la_pagina(eventos: list[dict], ciclos: list[dict], lugares: dict[str, dict], hoy) -> list[dict]:
    """Los eventos especiales, cada uno con sus actividades listas para mostrar (fecha, título, sala y enlace)."""
    armados = especiales.armar(eventos, ciclos, hoy)
    for especial in armados:
        especial["actividades"] = [
            {
                "titulo": e["titulo"],
                "url": (entrada_principal(e) or e["fuentes"][0])["url"],
                "lugar": lugares.get(e["lugar_id"], {}).get("nombre", ""),
                # La primera función dentro de las fechas del especial.
                "cuando": next(
                    (fecha_corta(f["inicio"], f.get("sin_hora", False)) for f in e["funciones"] if f["inicio"][:10] >= especial["desde"].isoformat()),
                    fecha_corta(e["funciones"][0]["inicio"], e["funciones"][0].get("sin_hora", False)),
                ),
            }
            for e in especial["eventos"]
        ]
    return armados


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


# Para colorear el mapa. Los escenarios grandes (de unas mil personas o más) van por id; el resto, por el
# nombre de la sala o por lo que se hace ahí.
ESCENARIOS_GRANDES = {
    "antel-arena", "estadio-centenario", "velodromo-municipal", "teatro-de-verano", "auditorio-nacional-del-sodre",
    "teatro-solis", "montevideo-music-box", "rural-del-prado", "centro-de-eventos-latu", "palacio-penarol",
}
TIPOS_DE_LUGAR = {
    "grande": "Escenarios grandes", "sala": "Teatros, salas y centros culturales",
    "museo": "Museos y exposiciones", "otro": "Bares, clubes, plazas y otros",
}
_ES_MUSEO = re.compile(r"\b(museo|cabildo|subte|galer[ií]a)", re.I)
_ES_SALA = re.compile(r"teatr|\bsala\b|auditorio|cinemateca|cine\b|espacio|centro cultural|\bciclo", re.I)


def tipo_de_lugar(lugar_id: str, nombre: str, eventos_del_lugar: list[dict]) -> str:
    if lugar_id in ESCENARIOS_GRANDES:
        return "grande"
    categorias = Counter(e["categoria"] for e in eventos_del_lugar)
    de_museo = sum("museo" in e.get("etiquetas", []) for e in eventos_del_lugar)
    escenicas = sum(categorias[c] for c in ("teatro", "danza", "humor", "cine", "infantil"))
    if de_museo * 2 > len(eventos_del_lugar) > 0:
        return "museo"
    # La sala va antes que el museo: la Sala del Museo es de conciertos.
    if _ES_SALA.search(nombre):
        return "sala"
    if _ES_MUSEO.search(nombre):
        return "museo"
    if escenicas * 2 > len(eventos_del_lugar) > 0:
        return "sala"
    return "otro"


def en_cartel(evento: dict) -> bool:
    """Temporadas y muestras: muchas fechas a lo largo de varias semanas.

    En el calendario van aparte ("También en cartel") para que no tapen lo que pasa solo ese día.
    """
    dias = sorted({f["inicio"][:10] for f in evento["funciones"]})
    duracion = (datetime.fromisoformat(dias[-1]) - datetime.fromisoformat(dias[0])).days
    return len(dias) >= 6 and duracion >= 14


def datos_para_el_navegador(eventos: list[dict], lugares: dict[str, dict], ciclos: list[dict]) -> dict:
    """Versión compacta de los eventos para filtrar en el navegador."""
    por_lugar: dict[str, list[dict]] = {}
    for e in eventos:
        por_lugar.setdefault(e["lugar_id"], []).append(e)
    return {
        "eventos": [
            {
                "id": e["id"],
                "titulo": e["titulo"],
                "url": (entrada_principal(e) or e["fuentes"][0])["url"],
                "precioTexto": precio_texto(e.get("precio")),
                "categoria": e["categoria"],
                "enCartel": en_cartel(e),
                # Un subrubro sin botón propio (por ejemplo, rock_pop) va con "otros".
                "sub": e.get("subcategoria") if e.get("subcategoria") in SUBCATEGORIAS.get(e["categoria"], {}) else None,
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
            id_: {
                "nombre": l["nombre"], "lat": l.get("lat"), "lon": l.get("lon"), "direccion": l.get("direccion"),
                "tipo": tipo_de_lugar(id_, l["nombre"], por_lugar.get(id_, [])),
            }
            for id_, l in lugares.items()
        },
        "ciclos": {c["id"]: c["titulo"] for c in ciclos},
        "tiposDeLugar": TIPOS_DE_LUGAR,
        "categorias": CATEGORIAS,
        "subcategorias": SUBCATEGORIAS,
        "subcategoriasOtros": SUBCATEGORIAS_OTROS,
        "subcategoriasExperimentales": SUBCATEGORIAS_EXPERIMENTALES,
    }


def _en_linea(texto: str) -> str:
    """Enlaces y negritas de Markdown, con el resto del texto escapado. Solo enlaces web, mail o internos."""
    texto = html.escape(texto, quote=False)
    texto = re.sub(r"\[([^\]]+)\]\(((?:https?://|mailto:)[^)\s]+|[\w./#-][^)\s:]*)\)",
                   lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', texto)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", texto)


PAGINA_AGREGA = "agrega-tu-evento.html"


def formulario_para_agregar(config: dict) -> str | None:
    """El enlace del formulario de "Agregá tu evento" (Tally o Google Forms), o None si todavía no hay."""
    enlace = (config.get("formulario") or "").strip()
    return enlace if re.match(r"https://(docs\.google\.com/forms/|tally\.so/)", enlace) else None


def servicio_del_formulario(enlace: str | None) -> str | None:
    """Dónde está el formulario, para contarlo en la página y en Privacidad."""
    if not enlace:
        return None
    return "Tally" if "tally.so" in enlace else "Google Forms"


def robots_txt(url_sitio: str) -> str:
    """Todo el sitio se puede indexar; el sitemap dice qué páginas hay."""
    return f"User-agent: *\nAllow: /\n\nSitemap: {url_sitio}sitemap.xml\n"


def sitemap_xml(url_sitio: str, actualizado: str, con_agrega: bool = False) -> str:
    """Las páginas del sitio, con la fecha de la última actualización de la cartelera."""
    paginas = [("", "daily", "1.0"), ("que-es.html", "monthly", "0.5")]
    if con_agrega:
        paginas.append((PAGINA_AGREGA, "monthly", "0.5"))
    urls = "".join(
        f"  <url><loc>{url_sitio}{ruta}</loc><lastmod>{actualizado}</lastmod><changefreq>{frecuencia}</changefreq>"
        f"<priority>{prioridad}</priority></url>\n"
        for ruta, frecuencia, prioridad in paginas
    )
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>\n'


def markdown_simple(texto: str) -> Markup:
    """Lo poco de Markdown que usa el texto de la pestaña: párrafos, listas, títulos, enlaces y negritas.
    Un salto de línea simple se respeta (la firma, por ejemplo).

    Cada título principal ("# ¿Cómo funciona?") abre una sección desplegable, que llega hasta el título
    siguiente o hasta una línea "---" (lo que va después, como la despedida, queda siempre a la vista)."""
    bloques, abierta = [], False

    def cerrar():
        nonlocal abierta
        if abierta:
            bloques.append("</div></details>")
            abierta = False

    for bloque in re.split(r"\n\s*\n", texto.strip()):
        lineas = [l.rstrip() for l in bloque.splitlines()]
        if bloque.strip() == "---":
            cerrar()
        elif all(l.startswith("- ") for l in lineas):
            items = "".join(f"<li>{_en_linea(l[2:])}</li>" for l in lineas)
            bloques.append(f"<ul>{items}</ul>")
        elif titulo := re.match(r"(#{1,3})\s+(.*)", bloque):
            nivel = len(titulo.group(1)) + 1
            if nivel == 2:
                cerrar()
                bloques.append(f'<details class="pregunta" open><summary><h2>{_en_linea(titulo.group(2))}</h2></summary><div>')
                abierta = True
            else:
                bloques.append(f"<h{nivel}>{_en_linea(titulo.group(2))}</h{nivel}>")
        else:
            bloques.append(f"<p>{'<br>'.join(_en_linea(l) for l in lineas)}</p>")
    cerrar()
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
    entorno.filters["entrada_principal"] = entrada_principal
    entorno.filters["periodo_muestra"] = periodo_muestra
    entorno.filters["promos_ordenadas"] = promos_ordenadas

    por_categoria = Counter(e["categoria"] for e in eventos)
    por_lugar = Counter(e["lugar_id"] for e in eventos)
    promos = Counter(b["programa"] for e in eventos for b in e.get("beneficios", []))
    datos = datos_para_el_navegador(eventos, lugares, ciclos)

    # "Festivales" va como etiqueta aparte (incluye festivales de cualquier rubro).
    categorias = [(k, v, por_categoria[k]) for k, v in CATEGORIAS.items() if por_categoria[k] and k != "festival"]
    # Los botones de tipo de evento: "Museos" (una etiqueta) va junto a Exposiciones. Los que pasan de los
    # visibles quedan plegados detrás de "Más tipos".
    rubros = []
    for clave, nombre, _ in categorias:
        rubros.append(("categoria", clave, nombre))
        if clave == "exposicion":
            rubros.append(("etiqueta", "museo", "Museos"))
    if ("etiqueta", "museo", "Museos") not in rubros:
        rubros.append(("etiqueta", "museo", "Museos"))
    nombres_fuentes = [FUENTES[f] for f in sorted({p["fuente"] for e in eventos for p in e["fuentes"]}) if f in FUENTES]
    agrega = formulario_para_agregar(configuracion_agrega())
    pagina = entorno.get_template("index.html.j2").render(
        sitio=NOMBRE_SITIO,
        agrega_tu_evento=bool(agrega),
        url_sitio=URL_SITIO,
        eventos=eventos,
        lugares=lugares,
        ciclos={c["id"]: c for c in ciclos},
        categorias=categorias,
        nombres_categoria=CATEGORIAS,
        varios_barrios=VARIOS_BARRIOS,
        nombres_subcategoria={clave: nombre for opciones in SUBCATEGORIAS.values() for clave, nombre in opciones.items()},
        presupuestos=PRESUPUESTOS,
        salas=sorted(((l["id"], l["nombre"], por_lugar[l["id"]]) for l in lugares_lista), key=lambda s: s[1].lower()),
        promos=promos.most_common(),
        rubros=rubros,
        rubros_visibles=7,
        programas_visibles=6,
        fuentes={**FUENTES, **VIAS},
        solo_informacion=SOLO_INFORMACION,
        promos_visibles=PROMOS_VISIBLES,
        nombres_fuentes=nombres_fuentes,
        generado=fecha_corta(generado) if generado else "",
        cantidad_gratis=sum(1 for e in eventos if presupuesto(e.get("precio")) == "gratis"),
        cantidad_promos=sum(1 for e in eventos if e.get("beneficios")),
        cantidad_festivales=sum(1 for e in eventos if "festival" in e.get("etiquetas", [])),
        tipos_de_lugar=TIPOS_DE_LUGAR,
        # Apagados por ahora: ver `activo` en config/eventos_especiales.toml.
        con_especiales=especiales.activo(),
        especiales=especiales_para_la_pagina(eventos, ciclos, lugares, datetime.now(MONTEVIDEO).date())
        if especiales.activo() else [],
        # Un "<" en los datos podría cerrar el <script> donde van embebidos: va escapado (JSON lo lee igual).
        datos_json=json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c"),
    )

    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    shutil.copytree(AQUI / "estaticos", SALIDA)
    (SALIDA / "index.html").write_text(pagina, encoding="utf-8")
    if QUE_ES.exists():
        que_es = entorno.get_template("que-es.html.j2").render(
            sitio=NOMBRE_SITIO, url_sitio=URL_SITIO, contenido=markdown_simple(QUE_ES.read_text(encoding="utf-8")), nombres_fuentes=nombres_fuentes,
            agrega_tu_evento=bool(agrega), servicio_agrega=servicio_del_formulario(agrega),
        )
        (SALIDA / "que-es.html").write_text(que_es, encoding="utf-8")
    if agrega:
        (SALIDA / PAGINA_AGREGA).write_text(entorno.get_template("agrega.html.j2").render(
            sitio=NOMBRE_SITIO, url_sitio=URL_SITIO, formulario=agrega, servicio=servicio_del_formulario(agrega),
        ), encoding="utf-8")
    # Para los buscadores.
    (SALIDA / "robots.txt").write_text(robots_txt(URL_SITIO), encoding="utf-8")
    (SALIDA / "sitemap.xml").write_text(sitemap_xml(URL_SITIO, (generado or datetime.now().isoformat())[:10], bool(agrega)), encoding="utf-8")
    # Los afiches que mandan los organizadores (ver cartelera/scrapers/propuestos.py).
    if (DIR_DATOS / "afiches").is_dir():
        shutil.copytree(DIR_DATOS / "afiches", SALIDA / "afiches")
    # Los datos también quedan publicados, por si alguien quiere usarlos.
    for nombre in ("eventos.json", "lugares.json", "ciclos.json"):
        if (DIR_DATOS / nombre).exists():
            shutil.copy(DIR_DATOS / nombre, SALIDA / nombre)
    return SALIDA / "index.html"
