"""Sitios hechos con el "MVD CMS" de la Intendencia: Teatro Solís y Teatro de Verano.

El listado por período (`acategoriaperiodo.aspx`) trae, por espectáculo, la fecha en texto
("30 y 31 de octubre / 1, 7 y 8 de noviembre", "24 de noviembre, 17:00h"), la sala, el género y
el enlace de compra (casi siempre Tickantel, lo que permite cruzarlo de forma exacta).
"""

import html
import re
from datetime import date, datetime, time, timedelta

from cartelera.categorias import categoria_por_lugar, clasificar, esta_cancelado
from cartelera.extraer import fecha_sin_anio
from cartelera.geo import sin_tildes
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo

MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                      "septiembre", "octubre", "noviembre", "diciembre"], start=1)}
MESES["setiembre"] = 9
GENEROS = {"teatro": "teatro", "musica": "musica", "danza": "danza", "opera": "musica", "lirica": "musica",
           "conferencia": "charla", "charla": "charla", "infantil": "infantil", "humor": "humor", "cine": "cine",
           "exposicion": "exposicion", "carnaval": "carnaval", "visita": "tour"}
_TARJETA = re.compile(r'<div class="bloqueconmargen">(.*?)class="fill-btn"', re.S)


def funciones_de_texto(texto: str, hoy: date, zona) -> list[Funcion]:
    """'30 y 31 de octubre / 1, 7 y 8 de noviembre' o '24 de noviembre, 17:00h' -> funciones."""
    plano = sin_tildes(html.unescape(texto))
    hora = re.search(r"(\d{1,2})[:.](\d{2})\s*h", plano)
    funciones = []
    for dias, mes in re.findall(r"((?:\d{1,2}\s*(?:,|y)?\s*)+)\s*de\s+([a-z]+)", plano):
        if mes not in MESES:
            continue
        for dia in re.findall(r"\d{1,2}", dias):
            fecha = fecha_sin_anio(int(dia), MESES[mes], hoy)
            if not fecha:
                continue
            if hora:
                inicio = datetime.combine(fecha, time(int(hora.group(1)), int(hora.group(2))), tzinfo=zona)
                funciones.append(Funcion(inicio=inicio))
            else:
                funciones.append(Funcion(inicio=datetime.combine(fecha, time(0, 0), tzinfo=zona), sin_hora=True))
    return funciones


def leer_listado(pagina: str) -> list[dict]:
    """Tarjetas del listado por período: título, fecha en texto, sala, género, enlaces e imagen."""
    tarjetas = []
    for bloque, inicio in ((m.group(1), m.start()) for m in _TARJETA.finditer(pagina)):
        enlace = re.search(r'<a href="(https?://[^"]+-uc(\d+))"[^>]*>([^<]+)</a>', bloque)
        if not enlace:
            continue
        campo = lambda clase: (re.search(rf'<li class="{clase}">\s*(.*?)\s*</li>', bloque, re.S) or [None, ""])[1]  # noqa: E731
        compra = re.search(r'<li class="icticket"><a href="([^"]+)"', bloque)
        imagen = re.search(r'<img src="([^"]+)"', pagina[max(0, inicio - 600):inicio])
        tarjetas.append({
            "url": enlace.group(1), "id": enlace.group(2), "titulo": html.unescape(enlace.group(3)).strip(),
            "fecha": re.sub(r"<[^>]+>", " ", campo("icdia")), "sala": html.unescape(re.sub(r"<[^>]+>", "", campo("icsala"))).strip(),
            "genero": html.unescape(re.sub(r"<[^>]+>", "", campo("icgenero"))).strip(),
            "compra": compra.group(1) if compra else None, "imagen": imagen.group(1) if imagen else None,
        })
    return tarjetas


def armar_evento(tarjeta: dict, fuente: str, lugar: LugarCrudo, ahora: datetime, productor: str) -> EventoCrudo | None:
    if esta_cancelado(tarjeta["titulo"]):
        return None
    funciones = [
        f for f in funciones_de_texto(tarjeta["fecha"], ahora.date(), ahora.tzinfo)
        if (f.inicio.date() >= ahora.date() if f.sin_hora else f.inicio >= ahora - timedelta(hours=6))
    ]
    if not funciones:
        return None
    for funcion in funciones:
        funcion.sala = tarjeta["sala"] or None
    genero = sin_tildes(tarjeta["genero"])
    categoria = next((c for clave, c in GENEROS.items() if clave in genero), None)
    compra = tarjeta["compra"]
    return EventoCrudo(
        fuente=fuente,
        id_externo=tarjeta["id"],
        url=tarjeta["url"],
        titulo=tarjeta["titulo"],
        categoria=categoria or clasificar(tarjeta["titulo"], tarjeta["genero"], por_defecto=categoria_por_lugar(lugar.nombre)),
        categoria_segura=categoria is not None,
        lugar=lugar,
        funciones=funciones,
        entradas=[Entrada(url=compra, via="tickantel" if "tickantel" in compra else fuente)] if compra else [],
        imagen_url=tarjeta["imagen"],
        productor=productor,
        enlaces=[compra] if compra else [],
    )
