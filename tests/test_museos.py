"""Museos: exposiciones con su período (o "actuales" sin cierre) y actividades (MNAV, Gurvich, calendario del MEC)."""

from datetime import date, datetime

from cartelera.scrapers import gurvich, mapi, mec_museos, mnav, museos_im, torres_garcia
from cartelera.scrapers.muestras import funciones_de_muestra, periodo_por_meses


def test_periodo_por_meses():
    assert periodo_por_meses("Abril 2026 - Abril 2027") == (date(2026, 4, 1), date(2027, 4, 30))
    assert periodo_por_meses("Noviembre - Marzo 2027") == (date(2026, 11, 1), date(2027, 3, 31))
    assert periodo_por_meses("Junio 2026") is None


def test_una_muestra_es_un_dia_sin_hora_hasta_el_cierre_o_el_horizonte(ahora):
    cerca = funciones_de_muestra(date(2026, 8, 1), date(2026, 11, 2), ahora)
    assert [f.inicio.day for f in cerca] == [30, 31, 1, 2] and all(f.sin_hora for f in cerca)
    assert len(funciones_de_muestra(None, None, ahora)) == 31  # sin cierre: un mes, renovado en cada corrida


def test_cabildo_toma_lo_abierto_y_subte_lo_actual(pagina, ahora):
    cabildo, subte = museos_im.MUSEOS
    muestras = [m for t in museos_im.leer_tarjetas(pagina("museos_cabildo.html")) if (m := museos_im.armar_muestra(t, cabildo, ahora))]
    assert {m.titulo: m.hasta for m in muestras} == {
        "Infancias en la ciudad": date(2027, 4, 30), "Gabinete de curiosidades": date(2026, 10, 31),
    }  # la de 2023 ya cerró
    actuales = [m for t in museos_im.leer_tarjetas(pagina("museos_subte.html")) if (m := museos_im.armar_muestra(t, subte, ahora))]
    assert [m.titulo for m in actuales] == ["DANI UMPI: OBRA REUNIDA"]  # "Pasadas" no es una exposición
    assert actuales[0].muestra and actuales[0].hasta is None and actuales[0].precio.gratis


def test_mnav_exposiciones_proximas_y_actividades(pagina, ahora):
    exposiciones = [e for item in mnav.leer_listado(pagina("mnav_exposiciones.html")) if (e := mnav.armar_exposicion(*item, ahora))]
    assert [(e.titulo, e.hasta, e.funciones[0].inicio.date()) for e in exposiciones][:1] == [
        ("El Misterio - Linda Kohen", date(2027, 4, 4), date(2026, 11, 28)),
    ]
    # Cada uno con su enlace, no con el del menú del sitio que está antes de la lista.
    assert exposiciones[0].url.endswith("id=kohen2026") and exposiciones[0].imagen_url.endswith("p=kohen2026")
    actividades = [e for item in mnav.leer_listado(pagina("mnav_actividades.html")) if (e := mnav.armar_actividad(*item, ahora))]
    taller = actividades[0]
    assert "juegos" not in taller.url
    assert (taller.categoria, taller.funciones[0].inicio.isoformat()) == ("taller", "2026-11-04T16:30:00-03:00")


def test_torres_garcia_solo_las_actuales(pagina, ahora):
    muestras = [torres_garcia.armar_muestra(i, ahora) for i in torres_garcia.actuales(pagina("torres_garcia_exposiciones.html"))]
    assert [m.titulo for m in muestras] == ["Encandilar silencios - Estudiantes UCU", "150 Aniversario - Joaquín Torres García"]


def test_gurvich_exposicion_con_periodo_y_actividades(pagina, ahora):
    muestras = gurvich.exposiciones(pagina("gurvich_exposiciones.html"), ahora)
    assert [(m.titulo[:25], m.funciones[0].inicio.date(), m.hasta) for m in muestras] == [
        ("Gurvich y la voz de la ci", date(2026, 11, 5), date(2027, 6, 15)),
    ]  # las cerradas no entran y la que se repite en la página, una sola vez
    antes = ahora.replace(day=20)
    actividades = gurvich.actividades(pagina("gurvich_portada.html"), antes)
    assert [(a.titulo, a.funciones[0].inicio.date()) for a in actividades] == [
        ("Mes de la música", date(2026, 10, 29)),
    ]  # el título sin "| 29 de octubre"; la del 13 ya pasó


def test_mapi_actuales_sin_repetir(pagina, ahora):
    muestras = [m for i in mapi.actuales(pagina("mapi_exposiciones.html")) if (m := mapi.armar_muestra(i, ahora))]
    assert len(muestras) == 4 and len({m.url for m in muestras}) == 4
    assert all(m.muestra and m.hasta is None and m.imagen_url.startswith("https://mapi.uy/") for m in muestras)


def test_mec_solo_museos_de_montevideo(pagina, ahora):
    eventos = [e for i in mec_museos.leer_listado(pagina("mec_calendario.html")) if (e := mec_museos.armar_evento(i, ahora))]
    assert {e.lugar.nombre: e.categoria for e in eventos} == {
        "Museo Zorrilla": "tour", "Museo Gurvich": "exposicion", "Museo Nacional de Antropología": "otros",
    }  # el Museo Spikerman es en Treinta y Tres; el Sodre y los congresos no son museos
    zorrilla = next(e for e in eventos if e.lugar.nombre == "Museo Zorrilla")
    assert zorrilla.funciones[0].inicio.isoformat() == "2026-11-04T18:30:00-03:00"
    assert zorrilla.lugar.direccion.startswith("José Luis Zorrilla de San Martín 96")
