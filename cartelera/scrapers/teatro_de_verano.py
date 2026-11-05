"""Teatro de Verano (MVD CMS de la Intendencia). Pocos espectáculos, pero clave en verano y en Carnaval.

Las competencias de Carnaval (la Prueba de Admisión en noviembre, el Concurso Oficial y la Liguilla en el verano)
aparecen en el listado como un solo espectáculo ("10 al 16 de noviembre"), pero la ficha trae el fixture:
"Etapa 1 — Martes 10 de noviembre" y debajo "20:30 — La Malandra (Murga)". Cuando está, cada etapa es un evento
propio, con su noche y sus conjuntos (así se puede buscar a un conjunto y encontrar cuándo sale).
"""

import html
import re
from datetime import datetime, time, timedelta

from cartelera.categorias import clasificar, esta_cancelado
from cartelera.extraer import fecha_sin_anio, meta, precio_de, recortar, texto_plano
from cartelera.geo import sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo
from cartelera.scrapers.mvd_cms import MESES, funciones_de_texto

NOMBRE = "teatro_de_verano"
BASE = "https://teatrodeverano.montevideo.gub.uy"
LUGAR = LugarCrudo(nombre="Teatro de Verano Ramón Collazo", direccion="Rambla Wilson s/n, Parque Rodó")
_TARJETA = re.compile(
    r'<section class="img-item">.*?<img src="([^"]+)".*?<a href="([^"]+-uc(\d+))"[^>]*>([^<]+)</a>\s*</h2>\s*<p class="text[^"]*">([^<]*)</p>',
    re.S,
)
_COMPRA = re.compile(r'href="(https?://(?:www\.)?(?:tickantel\.com\.uy|redtickets\.uy|www\.redtickets\.uy|abitab\.com\.uy)[^"]*)"')


# "Etapa 1 — Martes 10 de noviembre" y todo lo que sigue hasta la próxima etapa. Sin distinguir mayúsculas y
# aceptando tildes en el día ("Miércoles", "Sábado").
_ETAPA = re.compile(
    r"Etapa\s+(\d+)\s*[—–-]+\s*[^\s\d]+\s+(\d{1,2})\s+de\s+([^\s\d]+)(.*?)(?=Etapa\s+\d+\s*[—–-]|$)", re.S | re.I,
)
# "20:30 — La Malandra (Murga)". El nombre no lleva números ni rayas (así no se cuela el pie de la página).
_CONJUNTO = re.compile(r"(\d{1,2}):(\d{2})\s*[—–-]+\s*([^()\d—–]{2,60}?)\s*\(([^()\d]{2,40})\)")
_ENTRADA = re.compile(r"Entrada libre[^.]*\.", re.I)


def leer_etapas(detalle: str, ahora: datetime) -> list[dict]:
    """El fixture de una competencia de Carnaval: [{numero, inicio, conjuntos: [(nombre, categoría)]}]."""
    texto = texto_plano(re.sub(r"(?s)<(script|style).*?</\1>", " ", detalle))
    etapas = []
    for encontrado in _ETAPA.finditer(texto):
        numero, dia, mes = int(encontrado.group(1)), int(encontrado.group(2)), sin_tildes(encontrado.group(3))
        if mes not in MESES:
            continue
        fecha = fecha_sin_anio(dia, MESES[mes], ahora.date())
        tramo = encontrado.group(4)
        conjuntos = [(nombre.strip(), categoria.strip()) for _, _, nombre, categoria in _CONJUNTO.findall(tramo)]
        primero = _CONJUNTO.search(tramo)
        if not fecha or not conjuntos or not primero:
            continue
        inicio = datetime.combine(fecha, time(int(primero.group(1)), int(primero.group(2))), tzinfo=ahora.tzinfo)
        etapas.append({"numero": numero, "inicio": inicio, "conjuntos": conjuntos})
    return etapas


def eventos_por_etapa(tarjeta: dict, detalle: str, ahora: datetime) -> list[EventoCrudo]:
    """Un evento por etapa: "Prueba de Admisión - Carnaval 2027 · Etapa 1: La Malandra, Desirée, …"."""
    entrada = _ENTRADA.search(texto_plano(detalle))
    eventos = []
    for etapa in leer_etapas(detalle, ahora):
        if etapa["inicio"] < ahora - timedelta(hours=6):
            continue
        nombres = [f"{nombre} ({categoria.lower()})" for nombre, categoria in etapa["conjuntos"]]
        lista = ", ".join(nombres[:-1]) + f" y {nombres[-1]}" if len(nombres) > 1 else nombres[0]
        descripcion = f"Etapa {etapa['numero']}: {lista}." + (f" {entrada.group(0)}" if entrada else "")
        eventos.append(EventoCrudo(
            fuente=NOMBRE,
            id_externo=f"{tarjeta['id']}-etapa-{etapa['numero']}",
            url=tarjeta["url"],
            # Los conjuntos van en el título: se ven en la tarjeta y la búsqueda los encuentra.
            titulo=f"{tarjeta['titulo']} · Etapa {etapa['numero']}: {', '.join(n for n, _ in etapa['conjuntos'])}",
            categoria="carnaval",
            categoria_segura=True,
            descripcion_corta=recortar(descripcion, 400),
            lugar=LUGAR,
            funciones=[Funcion(inicio=etapa["inicio"])],
            precio=precio_de(entrada.group(0)) if entrada else None,
            entradas=[Entrada(url=tarjeta["url"], via=NOMBRE)],
            imagen_url=tarjeta["imagen"],
            productor="Teatro de Verano",
        ))
    return eventos


def leer_programacion(pagina: str) -> list[dict]:
    return [
        {"imagen": imagen, "url": url, "id": id_, "titulo": html.unescape(titulo).strip(), "fecha": fecha}
        for imagen, url, id_, titulo, fecha in _TARJETA.findall(pagina)
    ]


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for tarjeta in leer_programacion(cliente.texto(f"{BASE}/categoria/Programacion-2")):
        if esta_cancelado(tarjeta["titulo"]):
            continue
        funciones = [
            f for f in funciones_de_texto(tarjeta["fecha"], ahora.date(), ahora.tzinfo)
            if (f.inicio.date() >= ahora.date() if f.sin_hora else f.inicio >= ahora - timedelta(hours=6))
        ]
        if not funciones:  # por ejemplo, "Prueba de admisión", sin fecha de espectáculo
            continue
        try:
            detalle = cliente.texto(tarjeta["url"])
        except Exception as error:  # noqa: BLE001
            errores.append(f"{tarjeta['url']}: {type(error).__name__}: {error}")
            continue
        por_etapa = eventos_por_etapa(tarjeta, detalle, ahora)
        if por_etapa:
            eventos.extend(por_etapa)
            continue
        compra = _COMPRA.search(detalle)
        compra = compra.group(1) if compra else None
        descripcion = meta(detalle, "og:description") or meta(detalle, "description")
        eventos.append(EventoCrudo(
            fuente=NOMBRE,
            id_externo=tarjeta["id"],
            url=tarjeta["url"],
            titulo=tarjeta["titulo"],
            categoria=clasificar(tarjeta["titulo"], descripcion, por_defecto="musica"),
            descripcion_corta=recortar(descripcion),
            lugar=LUGAR,
            funciones=funciones,
            entradas=[Entrada(url=compra, via="tickantel" if "tickantel" in compra else "redtickets" if "redtickets" in compra else "abitab")] if compra else [],
            imagen_url=tarjeta["imagen"],
            productor="Teatro de Verano",
            enlaces=[compra] if compra else [],
        ))
    return eventos, errores
