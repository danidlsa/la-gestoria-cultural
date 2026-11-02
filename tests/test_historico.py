"""Histórico privado: acumula las funciones de cada evento y lo archiva cuando termina o desaparece."""

import json
from datetime import datetime, timedelta

from cartelera import historico
from cartelera.scrapers.base import MONTEVIDEO

LUGARES = {"sodre": {"id": "sodre", "nombre": "Auditorio del Sodre", "direccion": "Andes", "lat": -34.9, "lon": -56.19}}


def evento(id_, *inicios, titulo="Obra"):
    return {
        "id": id_, "titulo": titulo, "categoria": "teatro", "lugar_id": "sodre", "descripcion_corta": "Una obra.",
        "funciones": [{"inicio": i, "sin_hora": False, "agotada": False} for i in inicios],
        "fuentes": [{"fuente": "sodre", "id_externo": "1", "url": "https://sodre.gub.uy/x", "visto": "…"}],
        "beneficios": [{"programa": "la diaria", "tipo": "2x1", "url": "https://x.uy"}],
    }


def dia(d, h=20):
    return datetime(2026, 11, d, h, tzinfo=MONTEVIDEO)


def leer_mes(directorio, mes):
    ruta = directorio / "eventos" / f"{mes}.jsonl"
    return [json.loads(l) for l in ruta.read_text().splitlines()] if ruta.exists() else []


def test_acumula_funciones_y_archiva_al_terminar(tmp_path):
    f1, f2 = dia(5).isoformat(), dia(6).isoformat()
    historico.actualizar(tmp_path, [evento("ev_a", f1, f2)], LUGARES, dia(2, 12))
    # El 6 la cartelera ya borró la función del 5: el histórico la conserva.
    historico.actualizar(tmp_path, [evento("ev_a", f2)], LUGARES, dia(6, 12))
    estado = historico.actualizar(tmp_path, [], LUGARES, dia(7, 12))
    assert estado == {"en_curso": 0, "nuevos": 0, "archivados": 1}
    [r] = leer_mes(tmp_path, "2026-11")
    assert r["estado"] == "realizado" and [f["inicio"] for f in r["funciones"]] == [f1, f2]
    assert r["primera_vez_visto"].startswith("2026-11-02T12:00") and r["ultima_vez_visto"].startswith("2026-11-06T12:00")
    assert r["lugar"]["nombre"] == "Auditorio del Sodre" and r["descripcion_corta"] == "Una obra."
    assert "visto" not in r["fuentes"][0] and "url" not in r["beneficios"][0]


def test_si_falta_un_dia_espera_y_si_no_vuelve_queda_desaparecido(tmp_path):
    futura = dia(20).isoformat()
    historico.actualizar(tmp_path, [evento("ev_b", futura)], LUGARES, dia(2))
    assert historico.actualizar(tmp_path, [], LUGARES, dia(3))["archivados"] == 0  # una fuente que falló un día
    historico.actualizar(tmp_path, [], LUGARES, dia(2) + timedelta(days=historico.DIAS_PARA_DESAPARECIDO + 1))
    [r] = leer_mes(tmp_path, "2026-11")
    assert r["estado"] == "desaparecido"


def test_lo_vigente_queda_en_curso(tmp_path):
    estado = historico.actualizar(tmp_path, [evento("ev_c", dia(25).isoformat())], LUGARES, dia(2))
    assert estado == {"en_curso": 1, "nuevos": 1, "archivados": 0}
    assert "ev_c" in json.loads((tmp_path / historico.EN_CURSO).read_text())
