"""Especiales con programa en un mapa de Google (la Noche de las Librerías 2026) y lo que vino con eso."""

from datetime import date, datetime

from cartelera import especiales
from cartelera.geocodificar import desabreviar
from cartelera.http import Robots
from cartelera.scrapers import mapas_especiales

from tests.conftest import MONTEVIDEO

NOCHE = {
    "id": "noche-de-las-librerias", "nombre": "La Noche de las Librerías", "desde": date(2026, 11, 13),
    "horario": ["19:00", "01:00"], "pagina": "https://eventos.montevideo.gub.uy/nochelibrerias",
    "regla": "meses", "meses": [11], "palabras": ["noche de (las )?librerias"],
}
AHORA = datetime(2026, 11, 7, 12, 0, tzinfo=MONTEVIDEO)


def _eventos(pagina):
    eventos, errores = mapas_especiales.eventos_del_mapa(pagina("noche_librerias_mapa.kml"), NOCHE, 2026, AHORA)
    assert errores == []
    return eventos


def test_cada_actividad_es_un_evento_con_su_libreria(pagina):
    eventos = _eventos(pagina)
    amazonia = [e for e in eventos if e.lugar.nombre == "Amazonia"]
    # Al campo suelto "Actividades" le falta la de las 19:00; la de "descripción" la trae: se juntan sin repetir.
    assert [e.funciones[0].inicio.strftime("%H:%M") for e in amazonia] == ["19:00", "19:45", "20:30", "21:15", "22:00", "23:00"]
    narrativas = amazonia[0]
    assert narrativas.titulo == "Narrativas del miedo"
    assert narrativas.descripcion_corta.startswith("Terror y suspenso")  # en mayúscula, aunque venía después de ":"
    assert (narrativas.lugar.direccion, narrativas.lugar.barrio) == ("Maldonado 1775", "Palermo")
    assert narrativas.ciclo == "La Noche de las Librerías 2026"
    assert narrativas.url == NOCHE["pagina"] and narrativas.entradas[0].via == "mapas_especiales"


def test_horarios_rangos_y_madrugada(pagina):
    adagio = next(e for e in _eventos(pagina) if e.lugar.nombre == "Adagio Librería Café")
    funcion = adagio.funciones[0]
    # "18:30 a 01:00 h": termina el sábado a la 1.
    assert (funcion.inicio.isoformat(), funcion.fin.isoformat()) == ("2026-11-13T18:30:00-03:00", "2026-11-14T01:00:00-03:00")


def test_lo_de_toda_la_noche_y_los_titulos_genericos(pagina):
    eventos = _eventos(pagina)
    charco = [e for e in eventos if e.lugar.nombre == "Club Cultural Charco"]
    # "Durante la noche: propuesta gastronómica…" es una actividad de toda la noche, no parte de la anterior.
    gastronomia = charco[-1]
    assert gastronomia.titulo.startswith("Propuesta gastronómica")
    assert (gastronomia.funciones[0].inicio.hour, gastronomia.funciones[0].fin.hour) == (19, 1)
    assert "Durante la noche" not in (charco[-2].descripcion_corta or "")
    # Sin ninguna hora: también queda, como algo de toda la noche.
    linardi = next(e for e in eventos if e.lugar.nombre == "Librería Linardi y Risso")
    assert linardi.titulo.startswith("La exposición de primeras ediciones")
    # "Charla. El libro de terror en Uruguay…": el título solo no dice nada.
    assert any(e.titulo == "Charla: El libro de terror en Uruguay" for e in eventos)


def test_tipos_de_actividad():
    assert mapas_especiales.tipo_de_actividad("Noche de jazz", "Presentación musical en vivo de un dúo") == "musica"
    assert mapas_especiales.tipo_de_actividad("Parque hotel", "Carlos Rehermann presenta su novela") == "charla"
    assert mapas_especiales.tipo_de_actividad("Taller de cosplay", "") == "taller"
    assert mapas_especiales.tipo_de_actividad("Cuentos con Grace", "Historias para disfrutar en familia") == "infantil"


def test_titulo_hasta_el_signo_de_pregunta():
    titulo, detalle = mapas_especiales.titulo_y_detalle("¿Cuántas mujeres caben en una misma mujer? Elisa Lieber conversa.")
    assert (titulo, detalle) == ("¿Cuántas mujeres caben en una misma mujer?", "Elisa Lieber conversa.")


def test_fecha_fija_y_actividades_de_madrugada():
    edicion = especiales.proxima_edicion(NOCHE | {"desde": date(2026, 11, 13)}, date(2026, 11, 7))
    assert (edicion["desde"], edicion["estimada"], edicion["a_confirmar"]) == (date(2026, 11, 13), False, False)
    assert edicion["ventana"] == (date(2026, 11, 13), date(2026, 11, 14))  # la 1 del sábado es de la noche del viernes
    evento = {"titulo": "Cierre musical", "ciclo_nombre": "La Noche de las Librerías 2026",
              "funciones": [{"inicio": "2026-11-14T00:30:00-03:00"}]}
    assert especiales.actividades(NOCHE, edicion["ventana"], [evento], {}) == [evento]


def test_se_muestran_solo_los_elegidos(tmp_path):
    config = tmp_path / "especiales.toml"
    config.write_text(
        'mostrar = ["b"]\n[[especial]]\nid = "a"\n[[especial]]\nid = "b"\n', encoding="utf-8",
    )
    assert [e["id"] for e in especiales.elegidos(config)] == ["b"]
    config.write_text('[[especial]]\nid = "a"\n[[especial]]\nid = "b"\n', encoding="utf-8")
    assert [e["id"] for e in especiales.elegidos(config)] == ["a", "b"]  # sin `mostrar`, todos


def test_robots_la_regla_mas_especifica_gana():
    robots = Robots()
    robots.parse([
        "User-agent: *", "Disallow: /maps/", "Allow: /maps/d/", "Disallow: /maps?", "Allow: /maps?*file=",
        "Disallow: /*.pdf$",
    ])
    assert robots.can_fetch("X", "https://www.google.com/maps/d/kml?mid=abc&forcekml=1")  # así lo lee Google
    assert not robots.can_fetch("X", "https://www.google.com/maps/place/x")
    assert robots.can_fetch("X", "https://www.google.com/maps?a=1&file=2")
    assert not robots.can_fetch("X", "https://www.google.com/maps?a=1")
    assert not robots.can_fetch("X", "https://x.com/doc.pdf") and robots.can_fetch("X", "https://x.com/doc.pdf?v=2")


def test_direcciones_sin_abreviaturas_para_openstreetmap():
    assert desabreviar("Av. Gral. Rivera 2298") == "Avenida General Rivera 2298"
    assert desabreviar("Dr. Tristán Narvaja 1528") == "Doctor Tristán Narvaja 1528"
    assert desabreviar("Maldonado 1775") == "Maldonado 1775"


def test_caminatas_una_sola_tabla_y_cache(tmp_path):
    from cartelera.caminatas import caminatas

    pedidos = []

    def pedir(coordenadas):
        pedidos.append(coordenadas)
        # a, b, c (en orden de id): a pie, b->a da un poco distinto que a->b
        return {"distances": [[0, 1000, 2000], [1010, 0, 1500], [2000, 1500, 0]],
                "durations": [[0, 720, 1440], [740, 0, 1080], [1440, 1080, 0]]}

    cache = tmp_path / "caminatas.json"
    lugares = {"b": (-34.90, -56.16), "a": (-34.91, -56.17), "c": (-34.92, -56.18)}
    tabla = caminatas(lugares, cache=cache, pedir=pedir)
    assert tabla["a|b"] == [1005, 12] and tabla["a|c"] == [2000, 24] and tabla["b|c"] == [1500, 18]
    assert len(pedidos) == 1
    assert caminatas(lugares, cache=cache, pedir=pedir) == tabla and len(pedidos) == 1  # de la caché
    # Un lugar que se mueve se vuelve a pedir.
    caminatas({**lugares, "c": (-34.93, -56.18)}, cache=cache, pedir=pedir)
    assert len(pedidos) == 2


def test_caminatas_sin_servicio_no_rompe(tmp_path):
    from cartelera.caminatas import caminatas

    def falla(_):
        raise ConnectionError("sin red")

    assert caminatas({"a": (-34.9, -56.1), "b": (-34.91, -56.1)}, cache=tmp_path / "c.json", pedir=falla) == {}


def test_cuando_termina_un_especial():
    noche = {"hasta": date(2026, 11, 13), "horario": ["19:00", "01:00"], "estimada": False, "a_confirmar": False}
    assert especiales.termina(noche).isoformat() == "2026-11-14T01:00:00-03:00"  # el sábado a la 1
    assert especiales.termina({**noche, "horario": ["10:00", "18:00"]}).isoformat() == "2026-11-13T18:00:00-03:00"
    assert especiales.termina({**noche, "horario": None}).isoformat() == "2026-11-14T00:00:00-03:00"
    assert especiales.termina({**noche, "a_confirmar": True}) is None
