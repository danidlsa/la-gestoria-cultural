"""Uso:
    python -m cartelera scrapear [fuente ...]   corre los scrapers (todos si no se indica ninguno)
    python -m cartelera scrapear --donde actions   solo las fuentes que corren en ese lugar (config/fuentes.toml)
    python -m cartelera unificar                arma datos/eventos.json y datos/lugares.json
    python -m cartelera sitio                   genera la web en sitio_generado/
    python -m cartelera avisos [--github]       eventos especiales que se acercan sin programa (con --github, abre issues)
    python -m cartelera historico --dir DIR     suma la cartelera al histórico privado (--reconstruir: desde la rama datos)
"""

import argparse
import logging
import sys
import tomllib
from pathlib import Path

from cartelera.scrapers import FUENTES
from cartelera.scrapers.base import correr


def main() -> int:
    parser = argparse.ArgumentParser(prog="cartelera")
    comandos = parser.add_subparsers(dest="comando", required=True)
    scrapear = comandos.add_parser("scrapear")
    scrapear.add_argument("fuentes", nargs="*", metavar="fuente", help=f"una o más de: {', '.join(FUENTES)}")
    scrapear.add_argument("--donde", choices=["actions", "local"], help="filtra por config/fuentes.toml")
    comandos.add_parser("unificar")
    comandos.add_parser("sitio")
    historico = comandos.add_parser("historico")
    historico.add_argument("--dir", required=True, type=Path, help="el clon del repo privado del histórico")
    historico.add_argument("--reconstruir", action="store_true", help="repasa todas las fotos de la rama datos (una sola vez)")
    avisos = comandos.add_parser("avisos")
    avisos.add_argument("--github", action="store_true", help="abre un issue por aviso (necesita gh y GH_TOKEN)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.comando == "scrapear":
        desconocidas = set(args.fuentes) - set(FUENTES)
        if desconocidas:
            parser.error(f"fuentes desconocidas: {', '.join(sorted(desconocidas))}")
        elegidas = args.fuentes or list(FUENTES)
        if args.donde:
            config = tomllib.loads(Path("config/fuentes.toml").read_text(encoding="utf-8"))
            elegidas = [f for f in elegidas if config.get(f, {}).get("corre_en") == args.donde]
        fallidas = []
        for nombre in elegidas:
            resultado = correr(FUENTES[nombre])
            logging.info("%s: %s eventos, ok=%s, %s errores", nombre, resultado.cantidad, resultado.ok, len(resultado.errores))
            if not resultado.ok:
                fallidas.append(nombre)
        return 1 if fallidas else 0
    if args.comando == "unificar":
        from cartelera.unificar import unificar
        unificar()
        return 0
    if args.comando == "sitio":
        from cartelera.sitio.generar import generar
        generar()
        return 0
    if args.comando == "historico":
        from cartelera import historico as h
        if args.reconstruir:
            pasos = h.reconstruir_desde_git(args.dir)
            logging.info("historico: %s fotos repasadas; en curso %s", len(pasos), pasos[-1]["en_curso"] if pasos else 0)
        else:
            logging.info("historico: %s", h.desde_datos(args.dir))
        return 0
    if args.comando == "avisos":
        from cartelera.especiales import avisar
        avisar(en_github=args.github)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
