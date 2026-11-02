"""Fuentes que corren local (no en GitHub Actions): portal de eventos IM, Sala Zitarrosa y Ticketmaster.uy."""

import json

from cartelera.scrapers import portal_im, ticketmaster_uy, zitarrosa
from cartelera.scrapers.portal_im import Indice


def _eventos_del_portal(pagina, ahora):
    respuesta = json.loads(pagina("portal_im_actividades.json"))
    indice = Indice(respuesta["included"])
    eventos = [e for a in respuesta["data"] for e in portal_im.armar_eventos(a, indice, ahora)]
    return portal_im.juntar_fechas(eventos)


def test_portal_im_une_fechas_sueltas_en_un_evento(pagina, ahora):
    eventos = {e.titulo: e for e in _eventos_del_portal(pagina, ahora)}
    murga = eventos["Murga Joven"]  # dos actividades, una por fecha, quedan en un solo evento
    assert [f.inicio.day for f in murga.funciones] == [15, 16]
    assert murga.ciclo == "Encuentro de Murga Joven 2026"
    assert (murga.categoria, murga.precio.gratis) == ("carnaval", True)
    assert murga.lugar.nombre == "Centro Cultural Las Duranas" and murga.lugar.lat < -34


def test_portal_im_expande_las_funciones_que_se_repiten(pagina, ahora):
    obra = {e.titulo: e for e in _eventos_del_portal(pagina, ahora)}["No te apures Luisa"]
    # Jueves y viernes del 22 de octubre al 4 de diciembre: quedan las que no pasaron.
    assert len(obra.funciones) == 11
    assert {f.inicio.strftime("%a %H:%M") for f in obra.funciones} == {"Thu 21:00", "Fri 21:00"}
    assert (obra.precio.desde, obra.precio.gratis) == (660, False)


def test_portal_im_suma_los_talleres_en_su_categoria(pagina, ahora):
    talleres = [e for e in _eventos_del_portal(pagina, ahora) if e.titulo == "Taller de Murga"]
    assert talleres and all((t.categoria, t.categoria_segura) == ("taller", True) for t in talleres)
    # Un día por semana en cada uno de tres lugares, hasta mediados de diciembre.
    assert sorted(len(t.funciones) for t in talleres) == [6, 6, 7]


def test_portal_im_descarta_lo_que_se_repite_sin_fin(ahora):
    todo_el_anio = {"value": "2026-03-16T17:00:00-03:00", "end_value": None,
                    "rrule": "FREQ=WEEKLY;INTERVAL=1;BYDAY=FR;UNTIL=20261212T150000Z"}
    sin_fin = {"value": "2026-03-16T17:00:00-03:00", "end_value": None, "rrule": "FREQ=WEEKLY;BYDAY=FR"}
    assert len(portal_im.funciones_de([todo_el_anio], ahora)) == 7  # los viernes del 30/10 al 11/12
    assert portal_im.funciones_de([sin_fin], ahora) is None


def test_portal_im_ordena_coordenadas_invertidas():
    lat, lon = portal_im.coordenadas("MULTIPOINT ((-34.868223 -56.332419), (-56.332373 -34.868394))")
    assert round(lat, 3) == -34.868 and round(lon, 3) == -56.332
    assert portal_im.coordenadas("POINT (-56.212201 -34.858549)") == (-34.858549, -56.212201)


def test_portal_im_titulos_con_fecha():
    assert portal_im.titulo_sin_fecha("Paseo Sur Palermo, sábado 14 de noviembre") == "Paseo Sur Palermo"
    assert portal_im.titulo_sin_fecha("Ida, la madre de Internet") == "Ida, la madre de Internet"


def test_portal_im_paraguas_con_el_programa_en_texto(pagina, ahora):
    """Música en el Parque no tiene actividades: sus fechas están en un texto ("Próximas fechas")."""
    respuesta = json.loads(pagina("portal_im_paraguas.json"))
    indice = Indice(respuesta["included"])
    eventos = [e for p in respuesta["data"] for e in portal_im.eventos_de_paraguas(p, indice, ahora)]
    parque = [e for e in eventos if e.ciclo == "Música en el Parque"]
    assert [(e.titulo, e.lugar.nombre, [f.inicio.strftime("%d/%m %H:%M") for f in e.funciones]) for e in parque] == [
        ("Música en el Parque", "Jardín Botánico", ["07/11 16:00"]),
        ("Música en el Parque", "Parque Villa Dolores", ["15/11 16:00"]),
        ("Música en el Parque", "Parque Villa García", ["22/11 18:00"]),
        ("Música en el Parque: Músicas Pioneras", "Las Pioneras", ["28/11 16:00", "29/11 16:00"]),
    ]
    assert all(e.categoria == "musica" and e.precio.gratis for e in parque)
    # Sin hora ni lugar en la línea: los del paraguas ("Ciudad Vieja", de 10 a 13).
    sabados = [e for e in eventos if e.ciclo == "Sábados en Ciudad Vieja"]
    assert [(e.lugar.nombre, e.funciones[0].inicio.strftime("%d/%m %H:%M")) for e in sabados] == [
        ("Ciudad Vieja", "21/11 10:00"), ("Ciudad Vieja", "19/12 10:00"),
    ]


def test_portal_im_linea_de_fecha():
    leer = lambda linea: portal_im.leer_linea_de_fecha(linea, lambda mes: 2026)  # noqa: E731
    dias, hora, subtitulo, lugar = leer("Sábado 28 y domingo 29 de noviembre, desde las 16:00 h, Músicas Pioneras en Las Pioneras.")
    assert ([d.day for d in dias], hora.hour, subtitulo, lugar) == ([28, 29], 16, "Músicas Pioneras", "Las Pioneras")
    assert leer("Sábado 21 de noviembre")[1:] == (None, None, None)
    assert leer("Los y las artistas se anunciarán cerca de la fecha.") is None


def test_zitarrosa_ficha_con_ciclo_precios_y_promos(pagina, ahora):
    url = "https://salazitarrosa.montevideo.gub.uy/espectaculo/natalie-perez-ciclo-marea/"
    evento = zitarrosa.parsear_ficha(pagina("zitarrosa_natalie.html"), url, ahora)
    assert (evento.titulo, evento.ciclo) == ("Natalie Pérez", "Ciclo MAREA")
    assert evento.funciones[0].inicio.isoformat() == "2026-11-14T20:30:00-03:00"
    assert evento.funciones[0].sala == "Sala Principal"
    assert (evento.precio.desde, evento.precio.hasta) == (1100, 1500)
    assert [b.programa for b in evento.beneficios] == ["la diaria", "Club El País"]
    assert evento.enlaces == ["https://tickantel.com.uy/inicio/alta_demanda/40021568/espectaculo/Natalie%20Perez"]
    assert (evento.categoria, evento.categoria_segura) == ("musica", True)


def test_zitarrosa_varias_funciones_y_hora_de_la_tarde(pagina, ahora):
    url = "https://salazitarrosa.montevideo.gub.uy/espectaculo/24-premios-graffiti/"
    evento = zitarrosa.parsear_ficha(pagina("zitarrosa_graffiti.html"), url, ahora)
    assert [f.inicio.strftime("%d/%m %H:%M") for f in evento.funciones] == ["04/11 21:00", "05/11 20:00"]
    assert evento.entradas[0].via == "zitarrosa"  # sin enlace de compra, se usa la ficha


def test_ticketmaster_toma_la_fecha_de_la_descripcion(pagina, ahora):
    datos = ticketmaster_uy.datos_de_ficha(pagina("ticketmaster_evento.html"))
    evento = ticketmaster_uy.armar_evento(datos, ahora)
    assert evento.titulo == "Foo Fighters - Take Cover Tour 2027"
    assert evento.funciones[0].inicio.date().isoformat() == "2027-02-23" and evento.funciones[0].sin_hora
    assert (evento.lugar.nombre, evento.categoria) == ("Centenario", "musica")
    assert ticketmaster_uy.slugs_de_portada("<a href='../event/foo-fighters-live-2027-mvd'>") == ["foo-fighters-live-2027-mvd"]


def test_portal_im_junta_en_una_tarjeta_lo_que_se_hace_en_muchos_lugares(pagina, ahora, monkeypatch):
    # El taller de murga del ejemplo se hace en 3 lugares: con el mínimo en 3, queda en una sola tarjeta.
    monkeypatch.setattr(portal_im, "MINIMO_PARA_JUNTAR_LUGARES", 3)
    taller = [e for e in _eventos_del_portal(pagina, ahora) if e.titulo == "Taller de Murga"]
    assert len(taller) == 1 and taller[0].lugar.nombre == "Varios barrios de Montevideo"
    assert taller[0].descripcion_corta.startswith("En 3 lugares: ")
    assert {f.sala for f in taller[0].funciones} == {"Centro Juvenil Salesiano", "Cooperativa 3 de Abril", "Cabaña Anaya"}
    assert len(taller[0].funciones) == 19

