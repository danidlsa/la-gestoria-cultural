"""Histórico de eventos para investigación: cada evento que ya pasó, con sus datos, en un repo privado.

La cartelera solo guarda lo vigente. Acá se lleva aparte, en un directorio (el clon del repo privado):

- `en_curso.json`: los eventos que todavía no terminaron. En cada corrida se actualizan con la cartelera nueva y
  se acumulan sus funciones (la cartelera va borrando las que ya pasaron).
- `eventos/AAAA-MM.jsonl`: una línea por evento terminado, en el archivo del mes de su última función.
  `estado` es "realizado" si su última función ya pasó, o "desaparecido" si dejó de estar en las fuentes antes
  de su fecha (se suspendió, se mudó o la fuente lo sacó) y no volvió en unos días.

Además de lo que muestra el sitio, cada evento lleva cuándo apareció por primera vez y cuándo se vio por última.
Guarda la descripción corta de la fuente: el repo es privado, para investigación, y no se redistribuye.
"""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

EN_CURSO = "en_curso.json"
DIAS_PARA_DESAPARECIDO = 3  # sin aparecer en las fuentes y con funciones por delante: se da por suspendido


def registro(evento: dict, lugares: dict[str, dict]) -> dict:
    """Los datos de un evento que vale la pena guardar, con su lugar completo (no solo el id)."""
    lugar = lugares.get(evento["lugar_id"], {})
    return {
        "id": evento["id"],
        "titulo": evento["titulo"],
        "categoria": evento["categoria"],
        "subcategoria": evento.get("subcategoria"),
        "etiquetas": evento.get("etiquetas", []),
        "descripcion_corta": evento.get("descripcion_corta"),
        "productor": evento.get("productor"),
        "ciclo": evento.get("ciclo_nombre"),
        "muestra": evento.get("muestra", False),
        "hasta": evento.get("hasta"),
        "lugar": {
            "id": evento["lugar_id"],
            "nombre": lugar.get("nombre"),
            "direccion": lugar.get("direccion"),
            "lat": lugar.get("lat"),
            "lon": lugar.get("lon"),
        },
        "funciones": [
            {clave: f.get(clave) for clave in ("inicio", "fin", "sin_hora", "sala", "agotada")}
            for f in evento.get("funciones", [])
        ],
        "precio": evento.get("precio"),
        "beneficios": [{"programa": b["programa"], "tipo": b.get("tipo")} for b in evento.get("beneficios", [])],
        "entradas": [{"url": e["url"], "via": e.get("via")} for e in evento.get("entradas", [])],
        "imagen_url": evento.get("imagen_url"),
        "fuentes": [
            {"fuente": f["fuente"], "id_externo": f.get("id_externo"), "url": f.get("url")} for f in evento.get("fuentes", [])
        ],
    }


def _unir_funciones(viejas: list[dict], nuevas: list[dict]) -> list[dict]:
    """Todas las funciones vistas alguna vez; de cada una, lo último que se supo (por ejemplo, si se agotó)."""
    por_inicio = {f["inicio"]: f for f in viejas}
    por_inicio.update({f["inicio"]: f for f in nuevas})
    return [por_inicio[inicio] for inicio in sorted(por_inicio)]


def _fin_del_evento(registro_: dict) -> datetime | None:
    inicios = [datetime.fromisoformat(f["inicio"]) for f in registro_["funciones"]]
    return max(inicios) if inicios else None


def actualizar(directorio: Path, eventos: list[dict], lugares: dict[str, dict], ahora: datetime) -> dict:
    """Suma una foto de la cartelera al histórico. Devuelve cuántos eventos hay en curso, nuevos y archivados."""
    ruta_en_curso = directorio / EN_CURSO
    en_curso: dict[str, dict] = json.loads(ruta_en_curso.read_text(encoding="utf-8")) if ruta_en_curso.exists() else {}
    marca = ahora.isoformat(timespec="minutes")
    nuevos = 0

    for evento in eventos:
        actual = registro(evento, lugares)
        anterior = en_curso.get(actual["id"])
        if anterior:
            actual["funciones"] = _unir_funciones(anterior["funciones"], actual["funciones"])
            actual["primera_vez_visto"] = anterior["primera_vez_visto"]
        else:
            actual["primera_vez_visto"] = marca
            nuevos += 1
        actual["ultima_vez_visto"] = marca
        en_curso[actual["id"]] = actual

    vistos_ahora = {e["id"] for e in eventos}
    archivados: dict[str, list[dict]] = {}
    for id_, guardado in list(en_curso.items()):
        if id_ in vistos_ahora:
            continue
        fin = _fin_del_evento(guardado)
        if fin is not None and fin < ahora:
            estado, mes = "realizado", fin.strftime("%Y-%m")
        elif ahora - datetime.fromisoformat(guardado["ultima_vez_visto"]) > timedelta(days=DIAS_PARA_DESAPARECIDO):
            estado, mes = "desaparecido", guardado["ultima_vez_visto"][:7]
        else:
            continue  # puede ser un día en que la fuente falló: se espera
        archivados.setdefault(mes, []).append({**guardado, "estado": estado})
        del en_curso[id_]

    (directorio / "eventos").mkdir(parents=True, exist_ok=True)
    for mes, registros in sorted(archivados.items()):
        with open(directorio / "eventos" / f"{mes}.jsonl", "a", encoding="utf-8") as archivo:
            for r in sorted(registros, key=lambda r: (r["funciones"][0]["inicio"] if r["funciones"] else "", r["id"])):
                archivo.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    ruta_en_curso.write_text(json.dumps(en_curso, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"en_curso": len(en_curso), "nuevos": nuevos, "archivados": sum(len(r) for r in archivados.values())}


def _leer_datos(directorio_datos: Path) -> tuple[list[dict], dict[str, dict], datetime]:
    eventos = json.loads((directorio_datos / "eventos.json").read_text(encoding="utf-8"))
    lugares = json.loads((directorio_datos / "lugares.json").read_text(encoding="utf-8"))
    return eventos["eventos"], {l["id"]: l for l in lugares["lugares"]}, datetime.fromisoformat(eventos["generado"])


def desde_datos(directorio: Path, directorio_datos: Path = Path("datos")) -> dict:
    """La corrida normal: suma la cartelera recién unificada."""
    eventos, lugares, generado = _leer_datos(directorio_datos)
    return actualizar(directorio, eventos, lugares, generado)


def reconstruir_desde_git(directorio: Path, rama: str = "origin/datos") -> list[dict]:
    """Repasa, de la más vieja a la más nueva, cada foto de la cartelera guardada en la rama de datos."""
    git = lambda *args: subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout  # noqa: E731
    resultados = []
    for commit in git("rev-list", "--reverse", rama).split():
        try:
            eventos = json.loads(git("show", f"{commit}:eventos.json"))
            lugares = json.loads(git("show", f"{commit}:lugares.json"))
        except subprocess.CalledProcessError:
            continue  # una foto sin cartelera (por ejemplo, la primera, vacía)
        generado = datetime.fromisoformat(eventos["generado"])
        resultados.append(actualizar(directorio, eventos["eventos"], {l["id"]: l for l in lugares["lugares"]}, generado))
    return resultados
