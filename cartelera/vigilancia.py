"""Vigila la tarea local desde GitHub Actions: si un día de semana no subió datos, abre un aviso (issue).

La tarea local (scripts/local/) corre los días de semana a las 11 en un equipo en Uruguay. Si ese día el equipo
no estuvo prendido o la corrida falló, sus fuentes quedan con el último resultado bueno y nadie se entera.
Como GitHub Actions corre igual, la corrida de la tarde mira cuándo fue la última vez que cada fuente local trajo
datos y, si no fue ese día, abre un issue (GitHub lo manda por mail). Cuando vuelven a llegar datos, lo cierra.

Los issues del repo son públicos: el texto habla de "la tarea local", sin detalles del equipo.
"""

import json
import logging
import subprocess
import tomllib
from datetime import date, datetime, time, timedelta
from pathlib import Path

from cartelera.scrapers.base import DIR_FUENTES, MONTEVIDEO

CONFIG = Path("config/fuentes.toml")
HORA_DE_LA_TAREA = time(11, 0)
HORA_DEL_CHEQUEO = time(18, 0)  # a esta hora ya tendría que haber corrido, aunque el equipo se haya prendido tarde
TITULO = "La tarea local no subió datos el {dia}"
PREFIJO_TITULO = "La tarea local no subió datos"
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
log = logging.getLogger(__name__)


def fuentes_locales(config: Path = CONFIG) -> list[str]:
    datos = tomllib.loads(config.read_text(encoding="utf-8"))
    return sorted(f for f, v in datos.items() if v.get("corre_en") == "local")


def dia_esperado(ahora: datetime) -> date:
    """El último día de semana en que la tarea ya tendría que haber corrido (y que ya se puede chequear)."""
    dia = ahora.date()
    if ahora.time() < HORA_DEL_CHEQUEO:
        dia -= timedelta(days=1)
    while dia.weekday() >= 5:  # sábado o domingo: la tarea no corre
        dia -= timedelta(days=1)
    return dia


def atrasadas(ahora: datetime, fuentes: list[str], directorio: Path = DIR_FUENTES) -> dict[str, str | None]:
    """Las fuentes locales sin datos desde el día esperado: {fuente: fecha de su última corrida buena (o None)}."""
    limite = datetime.combine(dia_esperado(ahora), HORA_DE_LA_TAREA, tzinfo=MONTEVIDEO) - timedelta(hours=2)
    resultado = {}
    for fuente in fuentes:
        archivo = directorio / f"{fuente}.json"
        corrida = json.loads(archivo.read_text(encoding="utf-8"))["corrida"] if archivo.exists() else None
        if corrida is None or datetime.fromisoformat(corrida) < limite:
            resultado[fuente] = corrida
    return resultado


def aviso(ahora: datetime, atrasadas_: dict[str, str | None]) -> dict | None:
    if not atrasadas_:
        return None
    dia = dia_esperado(ahora)
    lineas = "\n".join(
        f"- `{fuente}`: último dato el {corrida[:16].replace('T', ' ')}" if corrida else f"- `{fuente}`: nunca"
        for fuente, corrida in sorted(atrasadas_.items())
    )
    return {
        "titulo": TITULO.format(dia=f"{DIAS[dia.weekday()]} {dia.day}/{dia.month}"),
        "cuerpo": (
            "La corrida local de los días de semana no trajo datos de estas fuentes:\n\n"
            f"{lineas}\n\n"
            "Puede ser que ese día el equipo no estuvo prendido, que no tenía conexión o que la corrida falló "
            "(por ejemplo, con una VPN que sale desde afuera de Uruguay). Mientras tanto, el sitio muestra el último "
            "resultado bueno de cada fuente.\n\n"
            "Este aviso se cierra solo cuando vuelven a llegar datos."
        ),
    }


def revisar(ahora: datetime | None = None, en_github: bool = False) -> dict | None:
    """Revisa la tarea local; con `en_github`, abre el aviso o cierra los anteriores si ya se resolvió."""
    ahora = ahora or datetime.now(MONTEVIDEO)
    pendiente = aviso(ahora, atrasadas(ahora, fuentes_locales()))
    if pendiente:
        log.info("vigilancia: %s", pendiente["titulo"])
    if not en_github:
        return pendiente
    from cartelera.especiales import crear_issues

    if pendiente:
        crear_issues([pendiente])
    else:
        cerrar_resueltos()
    return pendiente


def cerrar_resueltos() -> None:
    """Cierra los avisos abiertos de la tarea local: ya volvieron a llegar datos."""
    abiertos = json.loads(subprocess.run(
        ["gh", "issue", "list", "--state", "open", "--limit", "100", "--json", "number,title"],
        capture_output=True, text=True, check=True,
    ).stdout)
    for issue in abiertos:
        if issue["title"].startswith(PREFIJO_TITULO):
            subprocess.run(
                ["gh", "issue", "close", str(issue["number"]), "--comment", "La tarea local volvió a subir datos."],
                check=True,
            )
            log.info("vigilancia: cerrado «%s»", issue["title"])
