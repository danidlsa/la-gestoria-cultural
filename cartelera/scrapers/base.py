"""Corre un scraper y guarda su resultado sin pisar el último resultado bueno."""

import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from cartelera.http import Cliente
from cartelera.modelo import ResultadoFuente

MONTEVIDEO = ZoneInfo("America/Montevideo")
DIR_FUENTES = Path("datos/fuentes")
# Si una corrida trae menos de esta fracción de lo que trajo la anterior, se asume que algo se rompió.
CAIDA_SOSPECHOSA = 0.5
log = logging.getLogger(__name__)


def ruta(fuente: str) -> Path:
    return DIR_FUENTES / f"{fuente}.json"


def cargar(fuente: str) -> ResultadoFuente | None:
    archivo = ruta(fuente)
    if not archivo.exists():
        return None
    return ResultadoFuente.model_validate_json(archivo.read_text(encoding="utf-8"))


def guardar(resultado: ResultadoFuente) -> bool:
    """Escribe el resultado si es bueno. Devuelve False si se conservó el anterior."""
    anterior = cargar(resultado.fuente)
    if not resultado.ok:
        log.error("%s: corrida fallida, se conserva el resultado anterior", resultado.fuente)
        return False
    if anterior and anterior.cantidad >= 10 and resultado.cantidad < anterior.cantidad * CAIDA_SOSPECHOSA:
        log.error(
            "%s: trajo %s eventos contra %s de la corrida anterior; se conserva el anterior",
            resultado.fuente, resultado.cantidad, anterior.cantidad,
        )
        return False
    archivo = ruta(resultado.fuente)
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(resultado.model_dump_json(indent=1), encoding="utf-8")
    return True


def correr(modulo, cliente: Cliente | None = None) -> ResultadoFuente:
    ahora = datetime.now(MONTEVIDEO)
    errores: list[str] = []
    try:
        with cliente or Cliente() as http:
            eventos, errores = modulo.scrapear(http, ahora)
        # Una corrida es buena si trajo algo y la mayoría de las páginas se pudieron leer.
        ok = bool(eventos) and len(errores) <= max(5, len(eventos))
    except Exception as error:  # noqa: BLE001 - cualquier falla deja la corrida como fallida
        log.exception("%s: error general", modulo.NOMBRE)
        eventos, errores, ok = [], [f"{type(error).__name__}: {error}"], False
    resultado = ResultadoFuente(
        fuente=modulo.NOMBRE, corrida=ahora, ok=ok, cantidad=len(eventos), errores=errores[:50], eventos=eventos,
    )
    guardar(resultado)
    return resultado
