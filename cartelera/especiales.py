"""Eventos especiales: jornadas de una vez por año (Día del Patrimonio, Museos en la Noche, las Llamadas…).

Cada uno está en config/eventos_especiales.toml con la regla de su fecha. Acá se calcula la próxima edición,
se buscan sus actividades entre los eventos ya unificados y se arman los avisos para cuando se acerca la
fecha y todavía no hay programa.
"""

import calendar
import json
import logging
import re
import subprocess
import tomllib
from datetime import date, datetime, time, timedelta
from pathlib import Path

from dateutil.easter import easter

from cartelera.geo import sin_tildes
from cartelera.scrapers.base import MONTEVIDEO

CONFIG = Path("config/eventos_especiales.toml")
DIAS_DE_AVISO = 30  # cuántos días antes se avisa si todavía no hay programa
DIAS_SEMANA = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
NOMBRES_DIA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
NOMBRES_MES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
    "diciembre",
]
log = logging.getLogger(__name__)


def cargar(ruta: Path = CONFIG) -> list[dict]:
    return tomllib.loads(ruta.read_text(encoding="utf-8")).get("especial", [])


def activo(ruta: Path = CONFIG) -> bool:
    """Si la pestaña "Especiales" y sus avisos están en uso (`activo` en la configuración; si falta, sí)."""
    return tomllib.loads(ruta.read_text(encoding="utf-8")).get("activo", True)


def elegidos(ruta: Path = CONFIG) -> list[dict]:
    """Los especiales que se muestran, en el orden de `mostrar`. Sin `mostrar`, todos (como antes)."""
    config = tomllib.loads(ruta.read_text(encoding="utf-8"))
    todos = config.get("especial", [])
    if "mostrar" not in config:
        return todos
    por_id = {e["id"]: e for e in todos}
    return [por_id[i] for i in config["mostrar"] if i in por_id]


def _enesimo(anio: int, mes: int, dia_semana: int, ordinal: int) -> date:
    """El primer sábado, el segundo viernes… de un mes."""
    primero = date(anio, mes, 1)
    return primero + timedelta(days=(dia_semana - primero.weekday()) % 7 + 7 * (ordinal - 1))


def _edicion(especial: dict, anio: int) -> tuple[date, date]:
    """Desde y hasta de la edición de ese año, según la regla."""
    regla = especial["regla"]
    if regla == "semana_de_turismo":
        domingo = easter(anio)
        return domingo - timedelta(days=6), domingo
    if regla == "dia_del_mes":
        inicio = _enesimo(anio, especial["mes"], DIAS_SEMANA.index(especial["dia"]), especial.get("ordinal", 1))
        return inicio, inicio + timedelta(days=especial.get("dias", 1) - 1)
    if regla == "meses":
        meses = especial["meses"]
        return date(anio, meses[0], 1), date(anio, meses[-1], calendar.monthrange(anio, meses[-1])[1])
    raise ValueError(f"{especial['id']}: regla desconocida {regla!r}")


def proxima_edicion(especial: dict, hoy: date) -> dict:
    """La edición que viene (o la que está en curso): fechas y qué tan seguras son."""
    if especial.get("desde") and especial.get("hasta", especial["desde"]) >= hoy:
        desde, hasta = especial["desde"], especial.get("hasta", especial["desde"])
        # Una noche que termina de madrugada ("19:00" a "01:00"): lo de después de las 12 también es suyo.
        horario = especial.get("horario")
        termina = hasta + timedelta(days=1) if horario and horario[1] < horario[0] else hasta
        return {"desde": desde, "hasta": hasta, "estimada": False, "a_confirmar": False, "ventana": (desde, termina)}
    desde, hasta = _edicion(especial, hoy.year)
    if hasta < hoy:
        desde, hasta = _edicion(especial, hoy.year + 1)
    # Con una fecha estimada, las actividades se buscan en todo el mes: el año que la corren una semana, igual aparecen.
    if especial["regla"] == "dia_del_mes":
        ventana = (desde.replace(day=1), desde.replace(day=calendar.monthrange(desde.year, desde.month)[1]))
    else:
        ventana = (desde, hasta)
    return {
        "desde": desde, "hasta": hasta, "ventana": ventana,
        "estimada": especial["regla"] == "dia_del_mes", "a_confirmar": especial["regla"] == "meses",
    }


def actividades(especial: dict, ventana: tuple[date, date], eventos: list[dict], ciclos: dict[str, str]) -> list[dict]:
    """Los eventos que nombran al especial y tienen alguna función dentro de sus fechas."""
    patrones = [re.compile(p) for p in especial.get("palabras", [])]
    encontrados = []
    for evento in eventos:
        ciclo = ciclos.get(evento.get("ciclo_id") or "", "") or evento.get("ciclo_nombre") or ""
        texto = sin_tildes(f"{evento['titulo']} {ciclo}").lower()
        if not any(p.search(texto) for p in patrones):
            continue
        dias = [date.fromisoformat(f["inicio"][:10]) for f in evento["funciones"]]
        if any(ventana[0] <= d <= ventana[1] for d in dias):
            encontrados.append(evento)
    return sorted(encontrados, key=lambda e: e["funciones"][0]["inicio"])


def termina(especial: dict) -> datetime | None:
    """Cuándo termina la edición: con `horario`, a esa hora (la noche del viernes, el sábado a la 1); si no, al
    terminar su último día. Sin fecha confirmada, no se sabe."""
    hasta = especial.get("hasta")
    if not hasta or especial.get("estimada") or especial.get("a_confirmar"):
        return None
    horario = especial.get("horario")
    if horario:
        dia = hasta + timedelta(days=1) if horario[1] < horario[0] else hasta
        return datetime.combine(dia, time.fromisoformat(horario[1]), tzinfo=MONTEVIDEO)
    return datetime.combine(hasta + timedelta(days=1), time(0, 0), tzinfo=MONTEVIDEO)


def fecha_texto(desde: date, hasta: date, a_confirmar: bool) -> str:
    """'Viernes 11 de diciembre de 2026', 'Sábado 3 y domingo 4 de octubre de 2027', 'Noviembre de 2026'."""
    if a_confirmar:
        if desde.month == hasta.month:
            return f"{NOMBRES_MES[desde.month - 1].capitalize()} de {desde.year}"
        return f"Entre {NOMBRES_MES[desde.month - 1]} y {NOMBRES_MES[hasta.month - 1]} de {hasta.year}"
    dia = lambda d: f"{NOMBRES_DIA[d.weekday()]} {d.day}"  # noqa: E731
    mes = lambda d: f"de {NOMBRES_MES[d.month - 1]}"  # noqa: E731
    if desde == hasta:
        texto = f"{dia(desde)} {mes(desde)}"
    elif (hasta - desde).days == 1:
        texto = f"{dia(desde)}{'' if desde.month == hasta.month else ' ' + mes(desde)} y {dia(hasta)} {mes(hasta)}"
    else:
        texto = f"del {dia(desde)}{'' if desde.month == hasta.month else ' ' + mes(desde)} al {dia(hasta)} {mes(hasta)}"
    texto = f"{texto} de {hasta.year}"
    return texto[0].upper() + texto[1:]


def faltan_texto(desde: date, hasta: date, hoy: date, a_confirmar: bool) -> str:
    if desde <= hoy <= hasta:
        return "Este mes" if a_confirmar else ("¡Es hoy!" if desde == hasta else "¡Ya empezó!")
    # A menos de un mes, en días; si no, en meses.
    dias = (desde - hoy).days
    if dias < 30:
        if a_confirmar:
            return "En menos de un mes"  # sin fecha, contar días hasta el 1.º del mes engañaría
        return "Mañana" if dias == 1 else f"Faltan {dias} días"
    meses = max(1, round(dias / 30.4))
    return "En 1 mes" if meses == 1 else f"En {meses} meses"


def armar(eventos: list[dict], ciclos: list[dict], hoy: date, especiales: list[dict] | None = None) -> list[dict]:
    """Los especiales con su próxima edición y sus actividades, del más cercano al más lejano."""
    titulos_ciclos = {c["id"]: c["titulo"] for c in ciclos}
    armados = []
    for especial in elegidos() if especiales is None else especiales:
        edicion = proxima_edicion(especial, hoy)
        encontrados = actividades(especial, edicion["ventana"], eventos, titulos_ciclos)
        if edicion["a_confirmar"] and edicion["desde"] <= hoy and not encontrados:
            # Ya arrancó el mes y no hay nada: lo más probable es que haya pasado (los datos son solo de lo que viene).
            edicion = proxima_edicion(especial, edicion["hasta"] + timedelta(days=1))
            encontrados = actividades(especial, edicion["ventana"], eventos, titulos_ciclos)
        desde, hasta, estimada, a_confirmar = edicion["desde"], edicion["hasta"], edicion["estimada"], edicion["a_confirmar"]
        if encontrados and (estimada or a_confirmar):
            # Con programa, las fechas son las de sus actividades (dentro de la ventana de búsqueda).
            dias = sorted(
                d for e in encontrados for f in e["funciones"]
                if edicion["ventana"][0] <= (d := date.fromisoformat(f["inicio"][:10])) <= edicion["ventana"][1]
            )
            # Si caen dentro de la fecha estimada, se confirma esa (el Patrimonio son dos días aunque haya
            # actividades de uno solo); si no, el año la corrieron y valen las del programa.
            if not (estimada and desde <= dias[0] and dias[-1] <= hasta):
                desde, hasta = dias[0], dias[-1]
            estimada, a_confirmar = False, False
        armados.append({
            **{k: especial[k] for k in ("id", "nombre", "descripcion", "cuando", "sitio")},
            "pagina": especial.get("pagina"), "horario": especial.get("horario"),
            # La fecha cargada a mano (`desde`/`hasta`): cuando pasa, el especial se apaga y no salta a la del año que viene.
            "fecha_cargada": especial.get("hasta", especial.get("desde")),
            "lugares": especial.get("lugares", "lugares"),
            # El nombre de la pestaña cuando se muestra solo este: "Noche de las Librerías" (sin el artículo).
            "pestana": especial.get("pestana") or re.sub(r"^(La|El|Las|Los) ", "", especial["nombre"]),
            "pestana_corta": especial.get("pestana_corta"), "icono": especial.get("icono"), "enlace": especial.get("enlace"),
            "desde": desde, "hasta": hasta, "estimada": estimada, "a_confirmar": a_confirmar,
            "en_curso": desde <= hoy <= hasta,
            "dias_para": (desde - hoy).days,
            "fecha_texto": fecha_texto(desde, hasta, a_confirmar),
            "faltan_texto": faltan_texto(desde, hasta, hoy, a_confirmar),
            "eventos": encontrados,
        })
    return sorted(armados, key=lambda a: a["desde"])


def avisos(armados: list[dict], hoy: date) -> list[dict]:
    """Un aviso por especial que empieza dentro de un mes y todavía no tiene actividades cargadas."""
    pendientes = []
    for especial in armados:
        if especial["eventos"] or especial["dias_para"] > DIAS_DE_AVISO or especial["hasta"] < hoy:
            continue
        cuando = "la fecha todavía no está confirmada" if especial["a_confirmar"] else f"sería el {especial['fecha_texto'].lower()}"
        pendientes.append({
            "titulo": f"Se viene {especial['nombre']} {especial['desde'].year}: todavía no hay programa",
            "cuerpo": (
                f"{especial['nombre']} es {especial['cuando']} y {cuando}, pero ninguna fuente trae sus actividades.\n\n"
                f"- Revisar el sitio oficial: {especial['sitio']}\n"
                "- Si ya se anunció la fecha, cargarla en `config/eventos_especiales.toml` (`desde` y `hasta`).\n"
                "- Si el programa está en otro lado (un PDF, una página nueva), ver si se puede sumar como fuente.\n\n"
                "Este aviso lo abre solo la corrida de GitHub Actions; no se repite para la misma edición."
            ),
        })
    return pendientes


def crear_issues(pendientes: list[dict]) -> None:
    """Abre un issue por aviso, salvo que ya exista uno con el mismo título (abierto o cerrado)."""
    # Se comparan los títulos exactos (la búsqueda de GitHub se confunde con signos como ":" o "+").
    existentes = set(subprocess.run(
        ["gh", "issue", "list", "--state", "all", "--limit", "500", "--json", "title", "--jq", ".[].title"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines())
    for aviso in pendientes:
        if aviso["titulo"] in existentes:
            log.info("avisos: ya existe «%s»", aviso["titulo"])
            continue
        subprocess.run(["gh", "issue", "create", "--title", aviso["titulo"], "--body", aviso["cuerpo"]], check=True)
        log.info("avisos: abierto «%s»", aviso["titulo"])


def avisar(hoy: date | None = None, en_github: bool = False) -> list[dict]:
    """Lee los datos unificados y avisa (en el log y, si se pide, con un issue) lo que se viene sin programa."""
    if not activo():
        log.info("avisos: los eventos especiales están apagados (config/eventos_especiales.toml)")
        return []
    hoy = hoy or datetime.now(MONTEVIDEO).date()
    eventos = json.loads(Path("datos/eventos.json").read_text(encoding="utf-8"))["eventos"]
    ciclos = json.loads(Path("datos/ciclos.json").read_text(encoding="utf-8"))["ciclos"]
    pendientes = avisos(armar(eventos, ciclos, hoy), hoy)
    for aviso in pendientes:
        log.info("avisos: %s", aviso["titulo"])
    if en_github and pendientes:
        crear_issues(pendientes)
    return pendientes
