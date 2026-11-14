"""Los eventos que no salen en el sitio porque no se sabe dónde quedan, y el aviso en GitHub para corregirlos.

Sin coordenadas no se puede saber si un evento es en Montevideo, así que `unificar` lo deja afuera. Muchas veces es
del interior y está bien; otras, es una sala de Montevideo con un nombre nuevo, o un post de Instagram ya aprobado
con un lugar que el buscador de direcciones no encuentra. Para esos se abre un aviso (uno solo, que se va
actualizando): cuando aparece un lugar nuevo, se comenta (y GitHub manda el correo); cuando no queda ninguno, se cierra.
"""

import json
import logging
import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from cartelera.geo import menciona_otra_ciudad, sin_tildes
from cartelera.modelo import EventoCrudo

ARCHIVO = Path("datos/sin_ubicacion.json")
ETIQUETA = "sin-ubicacion"
MARGEN = 3  # horas: lo que empezó hace un rato todavía cuenta
log = logging.getLogger(__name__)

# Ciudades de fuera de Montevideo que no siempre van al final del nombre ("Teatro La Sala - Las Piedras").
_INTERIOR = re.compile(r"\b(las piedras|la paz|ciudad de la costa|el pinar|solymar|lagomar|pando|atlantida|parque del plata|"
                       r"la floresta|piriapolis|punta del este|jose ignacio|la barra|maldonado|polonio|la paloma|"
                       r"colonia del sacramento|minas|rocha|salto|paysandu|tacuarembo|rivera|treinta y tres)\b")


def del_interior(evento: EventoCrudo) -> bool:
    textos = [evento.lugar.nombre or "", evento.lugar.direccion or "", evento.titulo]
    return evento.region != "montevideo" or any(menciona_otra_ciudad(t) or _INTERIOR.search(sin_tildes(t)) for t in textos)


def guardar(descartados: list[EventoCrudo], ahora: datetime) -> list[dict]:
    """Los descartados que todavía no pasaron y no son del interior, en datos/sin_ubicacion.json."""
    items = []
    for e in descartados:
        proximas = sorted(f.inicio for f in e.funciones if (f.inicio - ahora).total_seconds() > -MARGEN * 3600)
        if not proximas or del_interior(e):
            continue
        items.append({"titulo": e.titulo, "lugar": e.lugar.nombre, "direccion": e.lugar.direccion, "fuente": e.fuente,
                      "url": e.url, "inicio": proximas[0].isoformat()})
    items.sort(key=lambda i: i["inicio"])
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.write_text(json.dumps({"generado": ahora.isoformat(), "eventos": items}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    return items


def _clave(lugar: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes(lugar or "sin-nombre")).strip("-")[:60]


INTRO = (
    "Estos eventos **no salen en el sitio** porque no se sabe dónde quedan: sin coordenadas no se puede saber si son "
    "en Montevideo. Los del interior ya están filtrados (si se coló alguno, se puede ignorar).\n\n"
    "Cómo se arreglan:\n"
    "- **Una sala de Montevideo con otro nombre** (\"Zavala Muniz | Teatro Solís\"): sumar el nombre como alias en "
    "`config/lugares_alias.toml`.\n"
    "- **Un post de Instagram**: poner `lat` y `lon` a la cuenta en `config/instagram_bares.toml`, o pedirle a Claude "
    "que mire la regla.\n\n"
    "Este aviso se actualiza solo y se cierra cuando no queda ninguno.\n"
)


def cuerpo(items: list[dict]) -> str:
    por_lugar: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for i in items:
        por_lugar[(i["lugar"] or "(sin nombre)", i["fuente"])].append(i)
    renglones = []
    # Primero lo que vino de Instagram: ya lo aprobaste y esperás verlo.
    for (lugar, fuente), eventos in sorted(por_lugar.items(), key=lambda kv: (kv[0][1] != "instagram_bares", kv[1][0]["inicio"])):
        direccion = f" ({eventos[0]['direccion']})" if eventos[0].get("direccion") else ""
        lista = "; ".join(f"[{e['titulo']}]({e['url']}) {datetime.fromisoformat(e['inicio']):%d/%m}" for e in eventos[:4])
        mas = f" y {len(eventos) - 4} más" if len(eventos) > 4 else ""
        renglones.append(f"- **{lugar}**{direccion} · `{fuente}` · {lista}{mas} <!-- lugar:{_clave(lugar)} -->")
    return INTRO + "\n" + "\n".join(renglones) + "\n"


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def avisar(en_github: bool = False) -> list[dict]:
    """Abre, actualiza o cierra el aviso de eventos sin ubicación."""
    try:
        items = json.loads(ARCHIVO.read_text(encoding="utf-8"))["eventos"]
    except (FileNotFoundError, ValueError, KeyError):
        return []
    for i in items:
        log.info("sin ubicación: %s (%s, %s)", i["titulo"], i["lugar"], i["fuente"])
    if not en_github or not os.environ.get("GH_TOKEN"):
        return items
    try:
        abiertos = json.loads(_gh("issue", "list", "--label", ETIQUETA, "--state", "open", "--json", "number,body") or "[]")
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        log.warning("sin ubicación: no se pudieron leer los avisos de GitHub (%s)", error)
        return items
    abierto = abiertos[0] if abiertos else None
    if not items:
        if abierto:
            _gh("issue", "close", str(abierto["number"]), "--comment", "Ya no queda ningún evento sin ubicar.")
        return items
    nuevo = cuerpo(items)
    lugares = set(re.findall(r"<!-- lugar:([\w-]+) -->", nuevo))
    if abierto:
        antes = set(re.findall(r"<!-- lugar:([\w-]+) -->", abierto.get("body") or ""))
        if nuevo != abierto.get("body"):
            _gh("issue", "edit", str(abierto["number"]), "--body", nuevo)
        if lugares - antes:  # un comentario, para que llegue el correo
            n = len(lugares - antes)
            _gh("issue", "comment", str(abierto["number"]), "--body",
                f"{n} {'lugar nuevo' if n == 1 else 'lugares nuevos'} sin ubicar (arriba, en la lista).")
        return items
    subprocess.run(["gh", "label", "create", ETIQUETA, "--color", "F06C4F", "--force",
                    "--description", "Eventos que no salen por no saber dónde son"], check=False, capture_output=True)
    comando = ["issue", "create", "--title", f"Eventos sin ubicación ({len(lugares)} {'lugar' if len(lugares) == 1 else 'lugares'})",
               "--body", nuevo, "--label", ETIQUETA]
    repo = os.environ.get("GH_REPO", "")
    if "/" in repo:
        comando += ["--assignee", repo.split("/")[0]]  # asignado a la dueña del repo: le llega el correo
    _gh(*comando)
    return items
