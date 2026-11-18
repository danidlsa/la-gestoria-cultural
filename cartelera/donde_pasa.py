""""Dónde pasa": el tipo de lugar de cada sala (bares y cafés, espacios culturales, salas chicas y grandes, al aire libre).

La clasificación es a mano, por lugar, en config/donde_pasa.toml. Un lugar nuevo (una sala que aparece por primera
vez, un bar que sumamos de Instagram) queda sin etiqueta y no sale cuando alguien filtra por "Dónde pasa". Para que
no se pierda, se abre un aviso en GitHub con los lugares que tienen eventos y no están en ningún grupo (uno solo, que se
va actualizando como el de eventos sin ubicación: comenta cuando aparece un lugar nuevo y se cierra cuando no queda
ninguno).
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

CONFIG = Path("config/donde_pasa.toml")
DIR_DATOS = Path("datos")
ETIQUETA = "donde-pasa"
NO_APLICA = "no_aplica"  # el grupo de los que no llevan etiqueta a propósito (museos, cines, librerías…)
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


INTRO = (
    "Estos lugares tienen eventos pero **no tienen etiqueta de \"Dónde pasa\"**, así que no aparecen cuando alguien "
    "filtra por Bares y cafés, Espacios culturales, Salas chicas, Salas grandes o Al aire libre.\n\n"
    "Para arreglarlo, sumar el id de cada uno (el que va entre comillas invertidas) a su grupo en "
    "`config/donde_pasa.toml`: `bares`, `espacios` (espacios culturales de usos múltiples), `chicas` (salas de hasta unas 300 personas), `grandes` (más de 300), `aire_libre`, "
    "o `no_aplica` si es un museo, un cine, una librería, una discoteca o una dirección suelta.\n\n"
    "Este aviso se actualiza solo y se cierra cuando no queda ninguno.\n"
)


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
    return INTRO + "\n" + "\n".join(renglones) + "\n"


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
