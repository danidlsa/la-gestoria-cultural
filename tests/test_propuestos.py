"""'Agregá tu evento': la fuente que lee los eventos aprobados y la página del formulario."""

from cartelera.scrapers import propuestos
from cartelera.sitio.generar import formulario_para_agregar, sitemap_xml

# Así llega la pestaña pública de la planilla (Google Sheets en español, publicada como CSV).
CSV = """Marca temporal,Nombre del evento,Tipo de evento,Fecha,Hora,Otras fechas y horas (opcional),Nombre de la sala o lugar,Dirección,Precio,Link de entradas o de más información,Descripción corta
4/11/2026 12:30:00,Noche de jazz en el patio,Música,7/11/2026,21:00:00,"14/11 21:30
21/11",Patio Rondeau,Av. Rondeau 1904,$400,instagram.com/patiorondeau,"Trío de jazz, con jam abierta al final."
4/11/2026 13:00:00,Taller de grabado,Taller,15/11/2026,,,Casa Cultural,,Gratis,https://redtickets.uy/evento/TALLER/34000/,
3/10/2026 10:00:00,Algo que ya pasó,Teatro,10/10/2026,20:00:00,,Sala X,,,https://salax.uy,
5/11/2026 9:00:00,Show en el interior,Música,20/11/2026,21:00,,Teatro Larrañaga en Salto,,,https://ejemplo.uy,
5/11/2026 9:10:00,Sin link,Música,20/11/2026,21:00,,Sala Y,,,,
"""


def test_filas_por_encabezado():
    filas = propuestos.filas(CSV)
    assert len(filas) == 5
    assert filas[0]["lugar"] == "Patio Rondeau" and filas[0]["direccion"] == "Av. Rondeau 1904"
    assert filas[0]["otras"].startswith("14/11")  # "Otras fechas y horas" no se confunde con Fecha ni Hora


def test_encabezados_del_formulario_real(ahora):
    real = (
        'Marca temporal,Nombre del evento:,Tipo de evento,Fecha,Hora,"Si hay más de una fecha/funciones, agregalas '
        'como texto acá:",Nombre de la sala / Lugar,Dirección,Precio,Link de entradas o de más información,Descripción corta\n'
        '4/11/2026 15:00:00,Ciclo de cortos,Cine,12/11/2026,19:00:00,"19/11 19:00; 26/11 19:00",Sala Z,Calle 1234,Gratis,https://z.uy,Cortos uruguayos\n'
    )
    fila = propuestos.filas(real)[0]
    assert (fila["titulo"], fila["lugar"], fila["fecha"]) == ("Ciclo de cortos", "Sala Z", "12/11/2026")
    assert len(propuestos.armar_evento(fila, ahora).funciones) == 3


def test_encabezados_de_tally(ahora):
    tally = (
        "Submission ID,Respondent ID,Submitted at,Nombre del evento,Tipo de evento,Fecha,Hora,"
        "Otras fechas y horas (opcional),Nombre de la sala o lugar,Dirección,Precio,"
        "Link de entradas o de más información,Descripción corta\n"
        "abc,xyz,2026-11-05 15:00:00,Lectura de poemas,Charla,2026-11-20,19:30,,Bar Q,Calle 99,Gratis,https://q.uy,Poetas jóvenes\n"
    )
    fila = propuestos.filas(tally)[0]
    assert (fila["enviado"], fila["lugar"]) == ("2026-11-05 15:00:00", "Bar Q")
    evento = propuestos.armar_evento(fila, ahora)
    assert (evento.categoria, evento.funciones[0].inicio.isoformat()) == ("charla", "2026-11-20T19:30:00-03:00")


def test_con_columna_aprobado_solo_pasan_las_tildadas():
    tally = (
        "Submitted at,Nombre del evento,Fecha,Nombre de la sala o lugar,Link de entradas o de más información,Aprobado\n"
        "2026-11-05 18:52:01,Aprobado,2026-11-18,Sala A,https://a.uy,TRUE\n"
        "2026-11-05 18:55:24,Sin aprobar,2026-11-18,Sala B,https://b.uy,FALSE\n"
        "2026-11-05 18:56:00,Vacío,2026-11-18,Sala C,https://c.uy,\n"
    )
    assert [f["titulo"] for f in propuestos.filas(tally)] == ["Aprobado"]


def test_evento_propuesto(ahora):
    jazz = propuestos.armar_evento(propuestos.filas(CSV)[0], ahora)
    assert [f.inicio.isoformat() for f in jazz.funciones] == [
        "2026-11-07T21:00:00-03:00", "2026-11-14T21:30:00-03:00", "2026-11-21T00:00:00-03:00",
    ]
    assert jazz.funciones[-1].sin_hora
    assert (jazz.categoria, jazz.categoria_segura, jazz.precio.desde) == ("musica", True, 400)
    assert jazz.url == "https://instagram.com/patiorondeau" and jazz.entradas[0].via == "instagram"
    taller = propuestos.armar_evento(propuestos.filas(CSV)[1], ahora)
    assert (taller.categoria, taller.precio.gratis, taller.entradas[0].via) == ("taller", True, "redtickets")
    assert taller.funciones[0].sin_hora


def test_quedan_afuera_lo_pasado_el_interior_y_lo_incompleto(ahora):
    titulos = [e.titulo for f in propuestos.filas(CSV) if (e := propuestos.armar_evento(f, ahora))]
    assert titulos == ["Noche de jazz en el patio", "Taller de grabado"]


def test_scrapear_sin_formulario_no_pide_nada(monkeypatch, ahora):
    monkeypatch.setattr(propuestos, "configuracion", lambda: {"csv": ""})
    assert propuestos.scrapear(None, ahora) == ([], [])


def test_scrapear_avisa_lo_aprobado_que_esta_incompleto(monkeypatch, ahora):
    class Cliente:
        def texto(self, url):
            return CSV

    monkeypatch.setattr(propuestos, "configuracion", lambda: {"csv": "https://docs.google.com/spreadsheets/d/e/x/pub?output=csv"})
    eventos, errores = propuestos.scrapear(Cliente(), ahora)
    assert len(eventos) == 2
    assert errores == ["Sin link: falta la sala, el link o una fecha que se entienda"]  # lo pasado no es un error


def test_pagina_del_formulario():
    assert formulario_para_agregar({"formulario": ""}) is None
    assert formulario_para_agregar({"formulario": "https://ejemplo.com/form"}) is None
    assert formulario_para_agregar({"formulario": "https://docs.google.com/forms/d/e/ABC/viewform"}).endswith("/viewform")
    assert formulario_para_agregar({"formulario": "https://tally.so/r/zEN7OZ"}) == "https://tally.so/r/zEN7OZ"
    assert "agrega-tu-evento.html" in sitemap_xml("https://x.uy/", "2026-11-04", con_agrega=True)
    assert "agrega-tu-evento.html" not in sitemap_xml("https://x.uy/", "2026-11-04")
