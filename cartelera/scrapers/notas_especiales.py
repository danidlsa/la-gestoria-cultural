"""Programas de los eventos especiales publicados en una nota (una noticia de un municipio, con la grilla en el texto).

El Municipio B publica la Noche de los Cafés y Bares Notables como una noticia de su web: un título (h4) por bar con
su "Dirección:" abajo, y al final la "Grilla de espectáculos", un renglón por show:

    Garo en vivo - 21:30 horas - Bar Andorra

Cada renglón pasa a ser un evento, con el bar como sala y el especial como ciclo, así aparece en su pestaña, en la
agenda, en el mapa y en Mi plan. Qué nota leer está en config/eventos_especiales.toml: el especial lleva `nota` (la
dirección de la noticia), `desde` (el día) y `pagina` (el enlace de cada show). Se leen solo los que no pasaron.

Lo que los bares anuncian distinto (en su Instagram, por ejemplo) se corrige a mano en el especial, con un bloque
`[[especial.cambios]]` por renglón: `lugar` y `hora` ("20:00"), y `titulo` (el nuevo, o el de un show que la nota no
trae), `categoria` (si no es música), `en_lugar_de` (la hora del renglón de la nota que reemplaza, si cambió la hora;
conserva su id, y Mi plan no lo pierde) o `quitar = true`.
"""

import html
import re
from datetime import date, datetime, time, timedelta

from cartelera import especiales
from cartelera.categorias import clasificar, esta_cancelado
from cartelera.geo import sin_tildes
from cartelera.http import Cliente
from cartelera.modelo import Entrada, EventoCrudo, Funcion, LugarCrudo

NOMBRE = "notas_especiales"
PUEDE_ESTAR_VACIA = True  # fuera de temporada no hay ningún especial con nota

# "21 horas", "21:30 horas", "19.30 hs", "22 h": la parte del renglón que es la hora.
_HORA = re.compile(r"^(\d{1,2})(?:[:.](\d{2}))?\s*(?:horas?|hs?)\.?$", re.I)
_GRILLA = re.compile(r"<h[2-4][^>]*>\s*(?:grilla|programa(?:ci[oó]n)?)\b.*?</h[2-4]>(.*?)(?=<h[1-4]|</div>|$)", re.S | re.I)
_LUGAR = re.compile(r"<h4[^>]*>(.*?)</h4>(.*?)(?=<h[1-4]|$)", re.S | re.I)
_DIRECCION = re.compile(r"Direcci[oó]n\s*:?\s*(?:</strong>)?\s*:?\s*([^<]+)", re.I)
# Una actividad que arranca antes de esta hora es de la madrugada siguiente.
_MADRUGADA = 6


def _texto(fragmento: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


def _clave(nombre: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", sin_tildes(nombre).lower()).strip()


def direccion_buscable(direccion: str) -> str:
    """Una esquina como la entiende el geocodificador: "18 de Julio esquina Yi" -> "18 de Julio y Yi"; "Pablo de María
    entre Charrúa y Canelones" -> "Pablo de María y Charrúa" (la primera esquina de la cuadra)."""
    direccion = re.sub(r"\s+esq(?:uina|\.)?\s+", " y ", direccion, flags=re.I)
    entre = re.match(r"^(.+?)\s+entre\s+(.+?)\s+y\s+.+$", direccion, re.I)
    return f"{entre.group(1)} y {entre.group(2)}" if entre else direccion


def lugares_de(pagina: str) -> dict[str, tuple[str, str | None]]:
    """Los lugares de la nota: clave -> (nombre, dirección)."""
    lugares = {}
    for titulo, cuerpo in _LUGAR.findall(pagina):
        nombre = _texto(titulo)
        direccion = _DIRECCION.search(cuerpo)
        if nombre:
            lugares[_clave(nombre)] = (nombre, _texto(direccion.group(1)).strip(" :.") if direccion else None)
    return lugares


def _lugar(nombre: str, lugares: dict[str, tuple[str, str | None]]) -> tuple[str, str | None]:
    """El lugar de la grilla entre los de la nota: "Escaramuza" es "Escaramuza Libros y Café"."""
    clave = _clave(nombre)
    if clave in lugares:
        return lugares[clave]
    for otra, lugar in lugares.items():
        if f" {clave} " in f" {otra} " or f" {otra} " in f" {clave} ":
            return lugar
    return nombre, None


def grilla_de(pagina: str) -> list[dict]:
    """Los renglones de la grilla: título, hora y lugar ("Garo en vivo - 21:30 horas - Bar Andorra")."""
    encontrada = _GRILLA.search(pagina)
    if not encontrada:
        raise ValueError("la nota no tiene la grilla")
    shows = []
    for parrafo in re.findall(r"<p[^>]*>(.*?)</p>", encontrada.group(1), re.S | re.I):
        partes = [p.strip() for p in re.split(r"\s[-–—]\s", _texto(parrafo)) if p.strip()]
        posicion = next((i for i, p in enumerate(partes) if _HORA.match(p)), None)
        if posicion is None or posicion == 0 or posicion == len(partes) - 1:
            continue
        hora = _HORA.match(partes[posicion])
        shows.append({
            "titulo": " - ".join(partes[:posicion]),
            "hora": time(int(hora.group(1)) % 24, int(hora.group(2) or 0)),
            "lugar": " - ".join(partes[posicion + 1:]),
        })
    return shows


def _hora(texto: str) -> time:
    horas, _, minutos = texto.partition(":")
    return time(int(horas) % 24, int(minutos or 0))


def con_cambios(shows: list[dict], cambios: list[dict]) -> list[dict]:
    """La grilla de la nota con las correcciones a mano del especial (`[[especial.cambios]]`)."""
    shows = [dict(s) for s in shows]
    for cambio in cambios:
        clave, hora = _clave(cambio["lugar"]), _hora(cambio["hora"])
        buscada = _hora(cambio["en_lugar_de"]) if cambio.get("en_lugar_de") else hora
        del_lugar = [s for s in shows if s["hora"] == buscada and (
            _clave(s["lugar"]) == clave or f" {clave} " in f" {_clave(s['lugar'])} " or f" {_clave(s['lugar'])} " in f" {clave} ")]
        if cambio.get("quitar"):
            shows = [s for s in shows if s not in del_lugar]
            continue
        if del_lugar:
            show = del_lugar[0]
            show.setdefault("hora_id", show["hora"])
            show["hora"] = hora
        else:
            show = {"lugar": cambio["lugar"], "hora": hora, "titulo": cambio.get("titulo", "")}
            shows.append(show)
        if cambio.get("titulo"):
            show["titulo"] = cambio["titulo"]
        if cambio.get("categoria"):
            show["categoria"] = cambio["categoria"]
    return [s for s in shows if s["titulo"]]


def eventos_de_la_nota(pagina: str, especial: dict, ahora: datetime) -> list[EventoCrudo]:
    dia: date = especial["desde"]
    lugares = lugares_de(pagina)
    ciclo = f"{especial['nombre']} {dia.year}"
    eventos = []
    for show in con_cambios(grilla_de(pagina), especial.get("cambios", [])):
        if esta_cancelado(show["titulo"]):
            continue
        nombre, direccion = _lugar(show["lugar"], lugares)
        hora = show["hora"]
        inicio = datetime.combine(dia + timedelta(days=1 if hora.hour < _MADRUGADA else 0), hora, tzinfo=ahora.tzinfo)
        eventos.append(EventoCrudo(
            fuente=NOMBRE,
            # Con el lugar y la hora: si suman un show, los demás conservan su id (y no se pierden de Mi plan).
            id_externo="-".join(_clave(x).replace(" ", "-")[:40]
                                for x in (especial["id"], str(dia.year), nombre, show.get("hora_id", hora).strftime("%H%M"))),
            url=especial["pagina"],
            titulo=show["titulo"],
            # Casi todo es música en vivo; lo que dice otra cosa ("Shows de bailes de Tango"), eso.
            categoria=show.get("categoria") or clasificar(show["titulo"], por_defecto="musica"),
            lugar=LugarCrudo(nombre=nombre, direccion=direccion_buscable(direccion) if direccion else None),
            funciones=[Funcion(inicio=inicio)],
            entradas=[Entrada(url=especial["pagina"], via=NOMBRE)],
            ciclo=ciclo,
            etiquetas=list(especial.get("etiquetas", [])),
        ))
    return eventos


def scrapear(cliente: Cliente, ahora: datetime) -> tuple[list[EventoCrudo], list[str]]:
    if not especiales.activo():
        return [], []
    eventos, errores = [], []
    for especial in especiales.cargar():
        dia = especial.get("desde")
        if not especial.get("nota") or not dia or especial.get("hasta", dia) < ahora.date():
            continue
        try:
            eventos += eventos_de_la_nota(cliente.texto(especial["nota"]), especial, ahora)
        except Exception as error:  # noqa: BLE001 - una nota rota no frena las demás
            errores.append(f"{especial['id']}: {type(error).__name__}: {error}")
    return eventos, errores
