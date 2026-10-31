"""Cartelera de Montevideo Portal: la mejor fuente agregada de teatro.

El listado de obras en cartel enlaza a la ficha de cada una, que trae género, resumen, localidades
(con promociones) y, por sala, cada función con su fecha y hora.
"""

import html
import logging
import re
from datetime import date, datetime, time, timedelta

from cartelera.beneficios import beneficios_de_entradas
from cartelera.categorias import esta_cancelado
from cartelera.extraer import precio_de, recortar, texto_plano
from cartelera.geo import sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo

NOMBRE = "cartelera_mvd"
BASE = "https://cartelera.montevideo.com.uy"
LISTADOS = {
    "teatro": f"{BASE}/apeliculafunciones.aspx?,,PELICULAS,OBRA,0,111",
    "infantil": f"{BASE}/apeliculafunciones.aspx?,,INFANTIL,OBRA,0,111",
}
MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                      "septiembre", "octubre", "noviembre", "diciembre"], start=1)}
MESES["setiembre"] = 9
log = logging.getLogger(__name__)


def ids_de_listado(pagina: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"averespectaculo\.aspx\?(\d+)", pagina)))


def fecha_de(texto: str, hoy: date) -> date | None:
    """'Viernes 30 de Octubre' -> la próxima fecha con ese día y mes (puede ser del año que viene)."""
    encontrado = re.search(r"(\d{1,2}) de ([a-záéíóú]+)", sin_tildes(texto))
    if not encontrado or encontrado.group(2) not in MESES:
        return None
    dia, mes = int(encontrado.group(1)), MESES[encontrado.group(2)]
    for anio in (hoy.year, hoy.year + 1):
        try:
            candidata = date(anio, mes, dia)
        except ValueError:
            return None
        if candidata >= hoy - timedelta(days=1):
            return candidata
    return None


def funciones_por_sala(pagina: str, hoy: date, zona) -> dict[str, list[Funcion]]:
    """{sala: [funciones]} a partir de la sección "Salas" de la ficha."""
    salas: dict[str, list[Funcion]] = {}
    seccion = pagina.split('class="salas-container"', 1)[-1]
    for bloque in re.split(r'<div class="heading-holder">', seccion)[1:]:
        nombre = re.search(r'<p class="heading small bold">(?:<a[^>]*>)?([^<]+)', bloque)
        if not nombre:
            continue
        funciones = []
        for dia_html, horas_html in re.findall(r'<p class="subheading">([^<]+)</p>\s*<ul>(.*?)</ul>', bloque, re.S):
            dia = fecha_de(html.unescape(dia_html), hoy)
            if not dia:
                continue
            for hora in re.findall(r'class="hour">\s*(\d{1,2})[:.](\d{2})', horas_html):
                funciones.append(Funcion(inicio=datetime.combine(dia, time(int(hora[0]), int(hora[1])), tzinfo=zona)))
        salas[html.unescape(nombre.group(1)).strip()] = funciones
    return salas


def _campo(texto: str, nombre: str) -> str | None:
    encontrado = re.search(rf"{nombre}:\s*(.+?)\s*(?:Título original|Duración|País|Autor|Dirección|Elenco|Ficha|Resumen|$)", texto)
    return encontrado.group(1).strip() if encontrado else None


def parsear_ficha(pagina: str, id_externo: str, categoria: str, hoy: date, zona) -> list[EventoCrudo]:
    """Un evento por sala (algunas obras se dan en más de una)."""
    texto = texto_plano(pagina)
    titulo = re.search(r"<h1[^>]*>\s*([^<]+?)\s*</h1>", pagina) or re.search(r"<title>\s*([^<]+?)\s*-\s*Cartelera", pagina)
    titulo = html.unescape(titulo.group(1)).strip() if titulo else ""
    if not titulo or esta_cancelado(titulo):
        return []
    genero = sin_tildes(_campo(texto, "Género") or "")
    if re.search(r"stand ?up|humor|monologo", genero):
        categoria = "humor"
    elif "danza" in genero:
        categoria = "danza"
    resumen = re.search(r"Resumen\s+(.+?)\s+(?:Funciones:|Localidades|Publicidad)", texto)
    localidades = re.search(r"Localidades\s+(.+?)\s+(?:Publicidad|Salas)", texto)
    localidades = localidades.group(1) if localidades else ""
    direccion = re.search(r"Funciones:.*?\(([^)]*\d[^)]*)\)", texto)
    imagen = re.search(r'<img[^>]+src="([^"]+imagenes_espectaculos[^"]+)"', pagina)
    url = f"{BASE}/averespectaculo.aspx?{id_externo}"

    salas = funciones_por_sala(pagina, hoy, zona)
    eventos = []
    for sala, funciones in salas.items():
        if not funciones:
            continue
        eventos.append(EventoCrudo(
            fuente=NOMBRE,
            id_externo=id_externo if len(salas) == 1 else f"{id_externo}-{sala}",
            url=url,
            titulo=titulo,
            categoria=categoria,
            categoria_segura=True,
            descripcion_corta=recortar(resumen.group(1) if resumen else None),
            lugar=LugarCrudo(nombre=sala, direccion=direccion.group(1).strip() if direccion and len(salas) == 1 else None),
            funciones=sorted(funciones, key=lambda f: f.inicio),
            precio=precio_de(localidades),
            entradas=[Entrada(url=url, via=NOMBRE)],
            beneficios=beneficios_de_entradas(re.split(r"\s+-\s+|\.\s", localidades), url),
            imagen_url=imagen.group(1) if imagen else None,
            productor=_campo(texto, "Dirección"),
        ))
    return eventos


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    # Una obra infantil puede aparecer en los dos listados: como el infantil va después, gana ese.
    categoria_de: dict[str, str] = {}
    for categoria, url in LISTADOS.items():
        for id_externo in ids_de_listado(cliente.texto(url)):
            categoria_de[id_externo] = categoria
    log.info("cartelera_mvd: %s obras en cartel", len(categoria_de))

    eventos, errores = [], []
    for id_externo, categoria in categoria_de.items():
        url = f"{BASE}/averespectaculo.aspx?{id_externo}"
        try:
            for evento in parsear_ficha(cliente.texto(url), id_externo, categoria, ahora.date(), ahora.tzinfo):
                evento.funciones = [f for f in evento.funciones if f.inicio >= ahora - timedelta(hours=6)]
                if evento.funciones:
                    eventos.append(evento)
        except Exception as error:  # noqa: BLE001 - una ficha rota no frena el resto
            errores.append(f"{url}: {type(error).__name__}: {error}")
    return eventos, errores
