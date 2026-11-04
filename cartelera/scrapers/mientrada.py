"""MiEntrada: ticketera de fiestas, recitales y shows (también del interior).

La agenda general se puede filtrar por departamento (`?estado=Montevideo`) y trae todos los eventos en una sola
página: título, día, hora de apertura (y a veces de inicio), sala e imagen. La ficha de cada evento suma la
descripción y confirma la ciudad en su JSON-LD. Ni la ficha ni la agenda dicen la dirección de la sala: la cartelera
la ubica por el nombre, como con otras fuentes.
"""

import re
from datetime import date, datetime, time

from cartelera.categorias import clasificar, es_deporte, esta_cancelado
from cartelera.extraer import jsonld_de_tipo, recortar, texto_plano
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo

NOMBRE = "mientrada"
BASE = "https://mientrada.com.uy"
AGENDA = f"{BASE}/agenda-geral?estado=Montevideo"
_TARJETA = re.compile(r'<div class="card-agenda-geral">(.*?)(?=<div class="card-agenda-geral">|</main>|$)', re.S)
_FECHA = re.compile(r"\b(\d{2})/(\d{2})/(\d{2})\b")
_APERTURA = re.compile(r"Apertura\s+(\d{1,2}):(\d{2})")
_INICIO = re.compile(r"Inicio\s+(\d{1,2}):(\d{2})")
HORA_DE_FIESTA = time(23, 0)
_DESCRIPCION = re.compile(r'<div id="texto-informacao"[^>]*>(.*?)</div>', re.S)


def leer_agenda(pagina: str) -> list[dict]:
    """Las tarjetas de la agenda: url, título, día, hora, sala e imagen."""
    tarjetas = []
    for bloque in _TARJETA.findall(pagina):
        enlace = re.search(r'href="(/evento/[^"]+)"', bloque)
        titulo = re.search(r"<h4[^>]*>(.*?)</h4>", bloque, re.S)
        texto = texto_plano(bloque)
        fecha = _FECHA.search(texto)
        if not enlace or not titulo or not fecha:
            continue
        # "Apertura 23:30 - Inicio 23:30": vale el inicio si lo dicen; si no, la apertura de puertas.
        hora = _INICIO.search(texto) or _APERTURA.search(texto)
        sala = re.findall(r'<p class="font-14" title="([^"]*)"', bloque)
        imagen = re.search(r'<img src="([^"]+)"', bloque)
        dia, mes, anio = (int(x) for x in fecha.groups())
        tarjetas.append({
            "url": BASE + enlace.group(1),
            "titulo": texto_plano(titulo.group(1)),
            "dia": date(2000 + anio, mes, dia),
            "hora": time(int(hora.group(1)), int(hora.group(2))) if hora else None,
            "sala": texto_plano(sala[-1]) if sala else "",
            "imagen": imagen.group(1) if imagen and "sem-imagem" not in imagen.group(1) else None,
        })
    return tarjetas


def leer_ficha(pagina: str) -> dict:
    """La descripción de la ficha y la ciudad que dice su JSON-LD."""
    descripcion = _DESCRIPCION.search(pagina)
    ciudad = None
    for evento in jsonld_de_tipo(pagina, "Event"):
        direccion = (evento.get("location") or {}).get("address") or {}
        ciudad = direccion.get("addressLocality") or direccion.get("addressRegion") or ciudad
    return {"descripcion": texto_plano(descripcion.group(1)) if descripcion else "", "ciudad": ciudad}


def armar_evento(tarjeta: dict, ficha: dict, ahora: datetime) -> EventoCrudo | None:
    titulo, descripcion = tarjeta["titulo"], ficha["descripcion"]
    if esta_cancelado(titulo) or es_deporte(titulo, descripcion) or tarjeta["dia"] < ahora.date():
        return None
    if ficha["ciudad"] and ficha["ciudad"].strip().lower() != "montevideo":
        return None
    # Sin nombre de sala (algunas fichas ponen solo la ciudad) no hay forma de ubicarlo.
    if not tarjeta["sala"] or tarjeta["sala"].strip().lower() == "montevideo":
        return None
    hora = tarjeta["hora"]
    # Si el texto no dice qué es: lo que abre a la medianoche es una fiesta; lo demás, un recital.
    categoria = clasificar(titulo, descripcion, por_defecto="")
    if not categoria:
        categoria = "fiesta" if hora and (hora >= HORA_DE_FIESTA or hora.hour < 6) else "musica"
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=tarjeta["url"].rsplit("-", 1)[-1],
        url=tarjeta["url"],
        titulo=titulo,
        categoria=categoria,
        descripcion_corta=recortar(descripcion),
        lugar=LugarCrudo(nombre=tarjeta["sala"]),
        funciones=[Funcion(
            inicio=datetime.combine(tarjeta["dia"], hora or time(0, 0), tzinfo=ahora.tzinfo), sin_hora=hora is None,
        )],
        entradas=[Entrada(url=tarjeta["url"], via=NOMBRE)],
        imagen_url=tarjeta["imagen"],
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for tarjeta in leer_agenda(cliente.texto(AGENDA)):
        if tarjeta["dia"] < ahora.date():
            continue
        try:
            armado = armar_evento(tarjeta, leer_ficha(cliente.texto(tarjeta["url"])), ahora)
        except Exception as error:  # noqa: BLE001 - una ficha rota no frena las demás
            errores.append(f"{tarjeta['url']}: {type(error).__name__}: {error}")
            continue
        if armado:
            eventos.append(armado)
    return eventos, errores
