"""Piano Piano (productora): la agenda de su web, WordPress con HTML del servidor.

Cada tarjeta trae título, tipo ("Concierto", "Obra", "Monólogo"), sala, fecha sin año y el enlace a las
entradas (RedTickets, Tickantel, el Antel Arena). Sirve para los anuncios tempranos: el mismo show
después aparece en la ticketera y se une por el enlace o por sala, día y título.
"""

import html
import re
from datetime import datetime, time

from cartelera.categorias import clasificar, es_deporte, esta_cancelado
from cartelera.extraer import texto_plano
from cartelera.geo import menciona_otra_ciudad, sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo
from cartelera.scrapers.cartelera_mvd import fecha_de

NOMBRE = "piano_piano"
BASE = "https://pianopiano.uy"
TIPOS = {
    "concierto": "musica", "show": "musica", "musical": "musica", "obra": "teatro", "monologo": "humor",
    "fiesta": "fiesta", "festival": "festival",
}
_TARJETA = re.compile(r'<a href="([^"]*)" class="card-agenda[^"]*">(.*?)</a>\s*</div>', re.S)
_VIAS = [("tickantel", "tickantel"), ("redtickets", "redtickets"), ("antelarena", "antel_arena")]


def leer_agenda(pagina: str) -> list[dict]:
    tarjetas = []
    for enlace, cuerpo in _TARJETA.findall(pagina):
        titulo = re.search(r"<h4>(.*?)</h4>", cuerpo, re.S)
        pie = re.findall(r"<span>([^<]+)</span>", cuerpo.split('class="foot', 1)[-1])
        fecha = re.search(r'<span class="date">\s*([^<]+?)\s*</span>', cuerpo)
        imagen = re.search(r"<img src='([^']+)'", cuerpo)
        pie = [html.unescape(p).strip() for p in pie]
        if titulo and fecha:
            tarjetas.append({
                "titulo": texto_plano(titulo.group(1)),
                # Algunas tarjetas no tienen tipo: entonces el único dato del pie es la sala.
                "tipo": pie[0] if len(pie) > 1 else "",
                "lugar": pie[-1] if pie else "",
                "fecha": html.unescape(fecha.group(1)),
                "enlace": html.unescape(enlace),
                "imagen": imagen.group(1) if imagen else None,
            })
    return tarjetas


def armar_evento(tarjeta: dict, ahora: datetime) -> EventoCrudo | None:
    titulo = re.sub(r"\s*[–-]\s*pr[oó]ximamente\s*$", "", tarjeta["titulo"], flags=re.I).strip()
    if not titulo or esta_cancelado(titulo) or es_deporte(titulo) or menciona_otra_ciudad(titulo):
        return None
    # "No Te Va Gustar en Montevideo", "Harlem Globetrotters – Montevideo": la ciudad sobra en el título.
    titulo = re.sub(r"\s*(?:\ben\b|[–-])\s*montevideo\s*$", "", titulo, flags=re.I).strip()
    dia = fecha_de(tarjeta["fecha"], ahora.date())
    if not dia or not tarjeta["lugar"]:
        return None
    tipo = TIPOS.get(sin_tildes(tarjeta["tipo"]))
    enlace = tarjeta["enlace"] if tarjeta["enlace"].startswith("http") else ""
    via = next((v for marca, v in _VIAS if marca in enlace), NOMBRE)
    return EventoCrudo(
        fuente=NOMBRE,
        id_externo=f"{dia.isoformat()}-{titulo}",
        url=f"{BASE}/agenda/",
        titulo=titulo,
        categoria=tipo or clasificar(titulo, por_defecto="musica"),
        categoria_segura=tipo is not None and tipo != "musica",
        lugar=LugarCrudo(nombre=tarjeta["lugar"]),
        funciones=[Funcion(inicio=datetime.combine(dia, time(0, 0), tzinfo=ahora.tzinfo), sin_hora=True)],
        entradas=[Entrada(url=enlace, via=via)] if enlace else [],
        imagen_url=tarjeta["imagen"],
        productor="Piano Piano",
        enlaces=[enlace] if enlace else [],
    )


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    eventos, errores = [], []
    for tarjeta in leer_agenda(cliente.texto(f"{BASE}/agenda/")):
        try:
            evento = armar_evento(tarjeta, ahora)
        except Exception as error:  # noqa: BLE001 - una tarjeta rota no frena el resto
            errores.append(f"{tarjeta.get('titulo')}: {type(error).__name__}: {error}")
            continue
        if evento:
            eventos.append(evento)
    return eventos, errores
