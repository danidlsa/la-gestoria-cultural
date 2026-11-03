"""Vigilancia de la tarea local: avisa si un día de semana no llegaron datos de sus fuentes."""

import json
from datetime import datetime

from cartelera import vigilancia
from cartelera.scrapers.base import MONTEVIDEO


def momento(dia, hora):
    return datetime(2026, 11, dia, hora, tzinfo=MONTEVIDEO)


def test_dia_esperado():
    assert vigilancia.dia_esperado(momento(3, 18)).day == 3  # martes a la tarde: el de hoy
    assert vigilancia.dia_esperado(momento(3, 12)).day == 2  # martes al mediodía: todavía se espera el de ayer
    assert vigilancia.dia_esperado(momento(7, 20)).day == 6  # sábado: el viernes
    assert vigilancia.dia_esperado(momento(9, 6)).day == 6  # lunes temprano: el viernes


def test_atrasadas_y_aviso(tmp_path):
    (tmp_path / "portal_im.json").write_text(json.dumps({"corrida": "2026-11-03T11:04:00-03:00"}))
    (tmp_path / "zitarrosa.json").write_text(json.dumps({"corrida": "2026-11-02T12:01:00-03:00"}))
    atrasadas = vigilancia.atrasadas(momento(3, 18), ["portal_im", "zitarrosa", "museos_im"], tmp_path)
    assert atrasadas == {"zitarrosa": "2026-11-02T12:01:00-03:00", "museos_im": None}
    aviso = vigilancia.aviso(momento(3, 18), atrasadas)
    assert aviso["titulo"] == "La tarea local no subió datos el martes 3/11"
    assert "`zitarrosa`: último dato el 2026-11-02 12:01" in aviso["cuerpo"] and "`museos_im`: nunca" in aviso["cuerpo"]
    assert "mac" not in aviso["cuerpo"].lower()  # los issues son públicos


def test_sin_atrasos_no_hay_aviso(tmp_path):
    (tmp_path / "portal_im.json").write_text(json.dumps({"corrida": "2026-11-03T15:30:00-03:00"}))
    assert vigilancia.aviso(momento(3, 18), vigilancia.atrasadas(momento(3, 18), ["portal_im"], tmp_path)) is None


def test_las_fuentes_locales_salen_de_la_config():
    assert {"portal_im", "zitarrosa", "ticketmaster_uy", "museos_im"} <= set(vigilancia.fuentes_locales())
