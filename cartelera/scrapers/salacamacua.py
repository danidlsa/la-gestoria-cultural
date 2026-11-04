"""Sala Camacuá (AEBU): música y teatro en Ciudad Vieja.

La portada (WordPress con All-in-One Event Calendar) trae cada evento en JSON-LD: nombre, fechas y descripción,
pero sin hora. La hora, la imagen y el link de venta salen de la ficha de cada evento ("Hora 20:30").

Un evento de varios días ("Nov 05 - 14", una obra) no dice qué días hay función: si se vende por una ticketera,
esas funciones exactas ya llegan por la ticketera y acá no se inventan; si no, se toma una función por día.
"""

import re
from datetime import date, datetime, time, timedelta

from cartelera.categorias import clasificar, esta_cancelado
from cartelera.extraer import jsonld_de_tipo, recortar, texto_plano
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo

NOMBRE = "salacamacua"
BASE = "https://www.salacamacua.uy"
LUGAR = LugarCrudo(nombre="Sala Camacuá", direccion="Camacuá 575, Ciudad Vieja")
MAXIMO_DIAS = 31  # un "evento" más largo es una temporada o una muestra: no se expande día por día
_HORA = re.compile(r"\bHora\s+(\d{1,2})[:.](\d{2})")
# Si la ficha no la dice, a veces está en el texto: "el 15 de noviembre a las 20:00 h".
_HORA_EN_TEXTO = re.compile(r"\ba las (\d{1,2})[:.](\d{2})\s*(?:h|hs|horas)?\b")
_TICKETERA = re.compile(r'href="(https?://(?:www\.)?(?:redtickets\.uy|tickantel\.com\.uy|passline\.com|mientrada\.com\.uy)[^"]+)"')
_IMAGEN_GENERICA = "Sala-Camacua"


def via_de(url: str) -> str:
    """La ticketera de un link de venta, con el nombre que usa la cartelera para sus fuentes."""
    for via in ("redtickets", "tickantel", "passline", "mientrada"):
        if via in url:
            return via
    return NOMBRE


def leer_ficha(pagina: str) -> dict:
    """La hora, el link de venta y la imagen de la ficha de un evento."""
    texto = texto_plano(re.sub(r"(?s)<(script|style).*?</\1>", "", pagina))
    hora = _HORA.search(texto)
    venta = _TICKETERA.search(pagina)
    imagen = re.search(r'<meta property="og:image" content="([^"]+)"', pagina)
    return {
        "hora": time(int(hora.group(1)), int(hora.group(2))) if hora else None,
        "venta": venta.group(1).replace("//servlet", "/servlet") if venta else None,
        "imagen": imagen.group(1) if imagen and _IMAGEN_GENERICA not in imagen.group(1) else None,
    }


def armar_evento(evento: dict, ficha: dict, ahora: datetime) -> EventoCrudo | None:
    titulo = texto_plano(evento.get("name"))
    url = (evento.get("offers") or {}).get("url") or evento.get("url")
    if not titulo or not url or not evento.get("startDate") or esta_cancelado(titulo):
        return None
    desde = date.fromisoformat(evento["startDate"][:10])
    hasta = date.fromisoformat((evento.get("endDate") or evento["startDate"])[:10])
    varios_dias = hasta > desde
    if varios_dias and (ficha["venta"] or (hasta - desde).days > MAXIMO_DIAS):
        return None  # las funciones exactas llegan por la ticketera (o es una temporada larga)
    descripcion = texto_plano(evento.get("description"))
    en_texto = _HORA_EN_TEXTO.search(descripcion)
    hora = ficha["hora"] or (time(int(en_texto.group(1)), int(en_texto.group(2))) if en_texto else None)
    dias = [desde + timedelta(days=i) for i in range((hasta - desde).days + 1)]
    funciones = [
        Funcion(inicio=datetime.combine(dia, hora or time(0, 0), tzinfo=ahora.tzinfo), sin_hora=hora is None)
        for dia in dias if dia >= ahora.date()
    ]
    if not funciones:
        return None
    # Es una sala de conciertos y teatro, no un tablado: el candombe o la murga canción acá son música.
    categoria = clasificar(titulo, descripcion, por_defecto="musica")
    entradas = [Entrada(url=ficha["venta"], via=via_de(ficha["venta"]))] if ficha["venta"] else []
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=url.rstrip("/").rsplit("/", 1)[-1],
        url=url,
        titulo=titulo,
        categoria="musica" if categoria == "carnaval" else categoria,
        descripcion_corta=recortar(descripcion),
        lugar=LUGAR,
        funciones=funciones,
        entradas=entradas + [Entrada(url=url, via=NOMBRE)],
        imagen_url=ficha["imagen"],
        productor="Sala Camacuá",
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for evento in jsonld_de_tipo(cliente.texto(f"{BASE}/"), "Event"):
        url = (evento.get("offers") or {}).get("url") or evento.get("url")
        if not url:
            continue
        try:
            armado = armar_evento(evento, leer_ficha(cliente.texto(url)), ahora)
        except Exception as error:  # noqa: BLE001 - una ficha rota no frena las demás
            errores.append(f"{url}: {type(error).__name__}: {error}")
            continue
        if armado:
            eventos.append(armado)
    return eventos, errores
