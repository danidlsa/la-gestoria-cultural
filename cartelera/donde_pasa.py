""""Dónde pasa": el tipo de lugar de cada sala (bares y cafés, espacios culturales, salas chicas y grandes, al aire libre).

La clasificación es a mano, por lugar, en config/donde_pasa.toml. "Al aire libre" es además una marca de cada evento
(ver al_aire_libre): el lugar da el valor de partida, el texto del evento lo corrige (una muestra adentro de un parque,
una caminata que sale de un museo) y, por encima de todo, van las excepciones a mano por link.

Un lugar nuevo (una sala que aparece por primera vez, un bar que sumamos de Instagram) queda sin etiqueta y no sale
cuando alguien filtra por "Dónde pasa". Para que no se pierda, se abre un aviso en GitHub con los lugares que tienen
eventos y no están en ningún grupo (uno solo, que se va actualizando como el de eventos sin ubicación: comenta cuando
aparece un lugar nuevo y se cierra cuando no queda ninguno).
"""

import json
import logging
import os
import re
import subprocess
import tomllib
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from cartelera.geo import sin_tildes

CONFIG = Path("config/donde_pasa.toml")
DIR_DATOS = Path("datos")
ETIQUETA = "donde-pasa"
NO_APLICA = "no_aplica"  # el grupo de los que no llevan etiqueta a propósito (museos, cines, librerías…)
AIRE_LIBRE = "aire_libre"
log = logging.getLogger(__name__)


def cargar(ruta: Path = CONFIG) -> tuple[dict[str, str], dict[str, str]]:
    """({clave: nombre} de los grupos que se muestran, {lugar_id: clave}). Los de "no aplica" no van en ninguno."""
    if not ruta.exists():
        return {}, {}
    config = tomllib.loads(ruta.read_text(encoding="utf-8"))
    grupos = {clave: grupo for clave, grupo in config.items() if clave != NO_APLICA}
    nombres = {clave: grupo["nombre"] for clave, grupo in grupos.items()}
    de_lugar = {lugar: clave for clave, grupo in grupos.items() for lugar in grupo.get("lugares", [])}
    return nombres, de_lugar


def reglas_aire_libre(ruta: Path = CONFIG) -> dict[str, set[str]]:
    """Lo que se suma a mano en [aire_libre]: lugares de otro grupo que también son al aire libre (tambien) y los
    eventos, por link, que sí o que no (si / no), digan lo que digan el lugar y el texto."""
    grupo = tomllib.loads(ruta.read_text(encoding="utf-8")).get(AIRE_LIBRE, {}) if ruta.exists() else {}
    return {clave: set(grupo.get(clave, [])) for clave in ("tambien", "si", "no")}


# Lo que dice el texto del evento (título y descripción, sin tildes). Primero lo que lo deja adentro aunque el lugar
# sea abierto: el lugar real no se sabe (un "lugar secreto", un meet & greet que se avisa antes, el bus que lleva a una
# fiesta) o es claramente bajo techo (una sala de proyección en un galpón).
_ADENTRO = re.compile(r"lugar secreto|se avisa(?:ra)? el lugar|detalles del lugar|meet\s*(?:&|and)\s*greet|\bm&g\b"
                      r"|\btransporte\b|sala de proyeccion|\bgalpon\b")
# Lo que lo hace al aire libre aunque el lugar no lo sea: lo dice, es en la calle, o es una caminata.
_AFUERA = re.compile(r"al aire libre|a la calle|caminata|walking tour|recorrido a pie|silent (?:horror )?tour"
                     r"|\bdesfile\b|(?<!baile de )\bllamadas\b")
# Una feria sola puede ser bajo techo (Espacio Modelo, un cowork): cuenta si dice que es en una plaza, parque, rambla
# o calle.
_FERIA_AFUERA = re.compile(r"\bferia\b.{0,80}\b(?:plaza|parque|rambla|calle)\b"
                           r"|\b(?:plaza|parque|rambla|calle)\b.{0,80}\bferia\b", re.S)


def al_aire_libre(evento: dict, de_lugar: dict[str, str], reglas: dict[str, set[str]]) -> bool:
    """Si el evento es al aire libre: excepción a mano por link > texto del evento > lugar."""
    links = {f.get("url") for f in evento.get("fuentes", [])}
    if links & reglas["no"]:
        return False
    if links & reglas["si"]:
        return True
    texto = sin_tildes(f"{evento.get('titulo') or ''} {evento.get('descripcion_corta') or ''}")
    if "al aire libre" not in texto and _ADENTRO.search(texto):
        return False
    if _AFUERA.search(texto) or _FERIA_AFUERA.search(texto):
        return True
    if evento.get("categoria") == "exposicion":  # una muestra en un parque o una plaza suele ser adentro de un edificio
        return False
    lugar = evento.get("lugar_id")
    return de_lugar.get(lugar) == AIRE_LIBRE or lugar in reglas["tambien"]


def donde(evento: dict, de_lugar: dict[str, str], reglas: dict[str, set[str]]) -> list[str]:
    """Los grupos de "Dónde pasa" de un evento: el de su lugar (salvo aire libre) y "aire_libre" si lo es. Un evento
    puede ser de dos (el Teatro de Verano es sala grande y al aire libre) o de ninguno (una muestra en una plaza)."""
    grupo = de_lugar.get(evento.get("lugar_id"))
    grupos = [grupo] if grupo and grupo != AIRE_LIBRE else []
    if al_aire_libre(evento, de_lugar, reglas):
        grupos.append(AIRE_LIBRE)
    return grupos


def clasificados(ruta: Path = CONFIG) -> set[str]:
    """Todos los lugares que ya se miraron: los de un grupo y los de "no aplica"."""
    if not ruta.exists():
        return set()
    config = tomllib.loads(ruta.read_text(encoding="utf-8"))
    return {lugar for grupo in config.values() for lugar in grupo.get("lugares", [])}


def pendientes(eventos: list[dict], lugares: dict[str, dict], ruta: Path = CONFIG) -> list[dict]:
    """Los lugares con eventos que no están clasificados, de más a menos eventos."""
    vistos = clasificados(ruta)
    por_lugar: dict[str, list[dict]] = defaultdict(list)
    for e in eventos:
        if e["lugar_id"] not in vistos:
            por_lugar[e["lugar_id"]].append(e)
    items = []
    for lugar_id, del_lugar in por_lugar.items():
        lugar = lugares.get(lugar_id, {})
        del_lugar.sort(key=lambda e: e["funciones"][0]["inicio"] if e["funciones"] else "")
        items.append({
            "id": lugar_id, "nombre": lugar.get("nombre") or lugar_id, "direccion": lugar.get("direccion"),
            "cantidad": len(del_lugar),
            "ejemplos": [{"titulo": e["titulo"], "categoria": e["categoria"],
                          "url": (e.get("fuentes") or [{}])[0].get("url"),
                          "inicio": e["funciones"][0]["inicio"] if e["funciones"] else None} for e in del_lugar[:3]],
        })
    return sorted(items, key=lambda i: (-i["cantidad"], i["nombre"]))


def cuerpo(items: list[dict]) -> str:
    renglones = []
    for i in items:
        direccion = f" ({i['direccion']})" if i.get("direccion") else ""
        ejemplos = "; ".join(
            (f"[{e['titulo']}]({e['url']})" if e.get("url") else e["titulo"])
            + (f" {datetime.fromisoformat(e['inicio']):%d/%m}" if e.get("inicio") else "")
            for e in i["ejemplos"])
        cuantos = f"{i['cantidad']} {'evento' if i['cantidad'] == 1 else 'eventos'}"
        renglones.append(f"- **{i['nombre']}**{direccion} · `{i['id']}` · {cuantos}: {ejemplos} <!-- lugar:{i['id']} -->")
    return "\n".join(renglones) + "\n"


def _leer(nombre: str):
    return json.loads((DIR_DATOS / nombre).read_text(encoding="utf-8"))


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def avisar(en_github: bool = False) -> list[dict]:
    """Abre, actualiza o cierra el aviso de lugares sin "Dónde pasa"."""
    try:
        datos_eventos, datos_lugares = _leer("eventos.json"), _leer("lugares.json")
    except (FileNotFoundError, ValueError):
        return []
    eventos = datos_eventos["eventos"] if isinstance(datos_eventos, dict) else datos_eventos
    lista = datos_lugares if isinstance(datos_lugares, list) else datos_lugares.get("lugares", datos_lugares)
    lugares = {l["id"]: l for l in (lista.values() if isinstance(lista, dict) else lista)}
    items = pendientes(eventos, lugares)
    for i in items:
        log.info("sin «Dónde pasa»: %s (%s, %s eventos)", i["nombre"], i["id"], i["cantidad"])
    if not en_github or not os.environ.get("GH_TOKEN"):
        return items
    try:
        abiertos = json.loads(_gh("issue", "list", "--label", ETIQUETA, "--state", "open", "--json", "number,body") or "[]")
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        log.warning("donde pasa: no se pudieron leer los avisos de GitHub (%s)", error)
        return items
    abierto = abiertos[0] if abiertos else None
    if not items:
        if abierto:
            _gh("issue", "close", str(abierto["number"]), "--comment", "Ya no queda ningún lugar sin etiqueta.")
        return items
    nuevo = cuerpo(items)
    ids = set(re.findall(r"<!-- lugar:([\w-]+) -->", nuevo))
    if abierto:
        antes = set(re.findall(r"<!-- lugar:([\w-]+) -->", abierto.get("body") or ""))
        if nuevo != abierto.get("body"):
            _gh("issue", "edit", str(abierto["number"]), "--body", nuevo)
        if ids - antes:  # un comentario, para que llegue el correo
            n = len(ids - antes)
            _gh("issue", "comment", str(abierto["number"]), "--body",
                f"{n} {'lugar nuevo' if n == 1 else 'lugares nuevos'} sin etiqueta (arriba, en la lista).")
        return items
    subprocess.run(["gh", "label", "create", ETIQUETA, "--color", "E4A94A", "--force",
                    "--description", "Lugares sin etiqueta de «Dónde pasa»"], check=False, capture_output=True)
    comando = ["issue", "create", "--title", f"Lugares sin «Dónde pasa» ({len(ids)})", "--body", nuevo, "--label", ETIQUETA]
    repo = os.environ.get("GH_REPO", "")
    if "/" in repo:
        comando += ["--assignee", repo.split("/")[0]]  # asignado a la dueña del repo: le llega el correo
    _gh(*comando)
    return items
