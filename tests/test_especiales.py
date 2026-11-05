"""Eventos especiales: la próxima edición según su regla, sus actividades y los avisos."""

from datetime import date

from cartelera import especiales

PATRIMONIO = {
    "id": "dia-del-patrimonio", "nombre": "Día del Patrimonio", "descripcion": "", "cuando": "el primer fin de semana de octubre",
    "sitio": "https://example.org/", "regla": "dia_del_mes", "mes": 10, "dia": "sabado", "ordinal": 1, "dias": 2,
    "palabras": ["dia del patrimonio"],
}
MUSEOS_NOCHE = {
    "id": "museos-en-la-noche", "nombre": "Museos en la Noche", "descripcion": "", "cuando": "un viernes de diciembre",
    "sitio": "https://example.org/", "regla": "dia_del_mes", "mes": 12, "dia": "viernes", "ordinal": 2,
    "palabras": ["museos en la noche"],
}
LIBRERIAS = {
    "id": "noche-de-las-librerias", "nombre": "La Noche de las Librerías", "descripcion": "", "cuando": "un viernes de noviembre",
    "sitio": "https://example.org/", "regla": "meses", "meses": [11], "palabras": ["noche de (las )?librerias"],
}


def evento(titulo, *inicios, ciclo=None):
    return {"titulo": titulo, "ciclo_id": ciclo, "funciones": [{"inicio": i} for i in inicios]}


def test_reglas_de_fecha():
    assert especiales.proxima_edicion(PATRIMONIO, date(2026, 9, 1))["desde"] == date(2026, 10, 3)  # 3 y 4 de octubre
    siguiente = especiales.proxima_edicion(PATRIMONIO, date(2026, 10, 5))  # ya pasó: la de 2027
    assert (siguiente["desde"], siguiente["hasta"], siguiente["estimada"]) == (date(2027, 10, 2), date(2027, 10, 3), True)
    turismo = especiales.proxima_edicion({"regla": "semana_de_turismo"}, date(2026, 10, 31))
    assert (turismo["desde"], turismo["hasta"]) == (date(2027, 3, 22), date(2027, 3, 28))  # Pascua 2027: 28 de marzo
    anunciada = especiales.proxima_edicion({**PATRIMONIO, "desde": date(2027, 10, 9), "hasta": date(2027, 10, 10)}, date(2027, 1, 1))
    assert (anunciada["desde"], anunciada["estimada"]) == (date(2027, 10, 9), False)


def test_con_programa_las_fechas_salen_de_las_actividades():
    eventos = [
        evento("Museos en la Noche 2026: videos en el Auditorio", "2026-12-04T20:00:00-03:00"),
        evento("Noche de museos y vinos", "2026-12-11T20:00:00-03:00"),  # no nombra al especial
        evento("Museos en la Noche 2025", "2025-12-12T20:00:00-03:00"),  # fuera de la ventana
    ]
    [armado] = especiales.armar(eventos, [], date(2026, 10, 31), [MUSEOS_NOCHE])
    assert [e["titulo"] for e in armado["eventos"]] == ["Museos en la Noche 2026: videos en el Auditorio"]
    # Se estimaba el segundo viernes (11), pero el programa dice el 4.
    assert (armado["desde"], armado["estimada"], armado["fecha_texto"]) == (date(2026, 12, 4), False, "Viernes 4 de diciembre de 2026")


def test_el_ciclo_tambien_cuenta():
    eventos = [evento("Visita guiada al Palacio", "2026-10-03T11:00:00-03:00", ciclo="c1")]
    [armado] = especiales.armar(eventos, [{"id": "c1", "titulo": "Día del Patrimonio 2026"}], date(2026, 9, 1), [PATRIMONIO])
    assert len(armado["eventos"]) == 1 and armado["fecha_texto"] == "Sábado 3 y domingo 4 de octubre de 2026"


def test_mes_empezado_sin_programa_pasa_al_anio_siguiente():
    [armado] = especiales.armar([], [], date(2026, 11, 20), [LIBRERIAS])
    assert (armado["fecha_texto"], armado["a_confirmar"]) == ("Noviembre de 2027", True)


def test_avisos_un_mes_antes_y_solo_sin_programa():
    hoy = date(2026, 10, 31)
    sin_programa = especiales.armar([], [], hoy, [LIBRERIAS, PATRIMONIO])
    assert [a["titulo"] for a in especiales.avisos(sin_programa, hoy)] == [
        "Se viene La Noche de las Librerías 2026: todavía no hay programa",
    ]  # el Día del Patrimonio 2027 está lejos
    con_programa = especiales.armar([evento("La Noche de las Librerías", "2026-11-20T19:00:00-03:00")], [], hoy, [LIBRERIAS])
    assert especiales.avisos(con_programa, hoy) == []


def test_la_config_es_valida():
    hoy = date(2026, 10, 31)
    for especial in especiales.cargar():
        edicion = especiales.proxima_edicion(especial, hoy)
        assert edicion["desde"] <= edicion["hasta"] and edicion["hasta"] >= hoy, especial["id"]
        assert especial["sitio"].startswith("https://") and especial["palabras"], especial["id"]


def test_cuanto_falta_en_meses_y_a_menos_de_un_mes_en_dias():
    hoy = date(2026, 10, 31)
    assert especiales.faltan_texto(date(2026, 11, 1), date(2026, 11, 1), hoy, False) == "Mañana"
    assert especiales.faltan_texto(date(2026, 11, 20), date(2026, 11, 20), hoy, False) == "Faltan 20 días"
    assert especiales.faltan_texto(date(2026, 11, 1), date(2026, 11, 30), hoy, True) == "En menos de un mes"
    assert especiales.faltan_texto(date(2026, 12, 4), date(2026, 12, 4), hoy, False) == "En 1 mes"
    assert especiales.faltan_texto(date(2027, 3, 22), date(2027, 3, 28), hoy, False) == "En 5 meses"
    assert especiales.faltan_texto(date(2027, 5, 1), date(2027, 5, 31), hoy, True) == "En 6 meses"


def test_se_pueden_apagar(tmp_path, monkeypatch):
    config = tmp_path / "especiales.toml"
    config.write_text('activo = false\n\n[[especial]]\nid = "x"\n', encoding="utf-8")
    assert especiales.activo(config) is False
    config.write_text('[[especial]]\nid = "x"\n', encoding="utf-8")
    assert especiales.activo(config) is True  # sin la clave, siguen como antes
    monkeypatch.setattr(especiales, "activo", lambda: False)
    assert especiales.avisar() == []  # apagados: no lee nada ni abre avisos
