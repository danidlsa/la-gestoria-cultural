import pytest

from cartelera.sitio.generar import en_cartel, fecha_corta, precio_texto, presupuesto


@pytest.mark.parametrize("precio, esperado", [
    ({"gratis": True}, "gratis"),
    ({"desde": 0, "hasta": 0}, "gratis"),
    ({"desde": 0, "hasta": 990}, "ganga"),  # una entrada a $0 entre pagas no hace gratis al evento
    ({"desde": 450}, "ganga"),
    ({"desde": 500}, "accesible"),
    ({"desde": 999}, "accesible"),
    ({"desde": 1000}, "normal"),
    ({"desde": 1600}, "normal"),
    ({"desde": 1601}, "carito"),
    ({"desde": None}, None),
    (None, None),
])
def test_presupuesto(precio, esperado):
    assert presupuesto(precio) == esperado


def test_textos():
    assert fecha_corta("2026-10-30T17:30:00-03:00") == "vie 30 oct · 17:30"
    assert fecha_corta("2026-11-01T00:00:00-03:00", sin_hora=True) == "dom 1 nov"
    assert precio_texto({"desde": 650, "hasta": 1200}) == "$650 a $1.200"
    assert precio_texto({"gratis": True}) == "Gratis"


def _con_dias(*dias):
    return {"funciones": [{"inicio": f"{d}T20:00:00-03:00"} for d in dias]}


def test_en_cartel():
    temporada = _con_dias(*[f"2026-11-{d:02d}" for d in (6, 7, 8, 13, 14, 15, 20, 21)])
    assert en_cartel(temporada)
    assert not en_cartel(_con_dias("2026-11-06", "2026-11-07", "2026-11-08"))  # pocas fechas
    assert not en_cartel(_con_dias(*[f"2026-11-{d:02d}" for d in range(1, 9)]))  # muchas, pero en una semana


def test_markdown_de_la_pestana_que_es():
    from cartelera.sitio.generar import markdown_simple
    salida = markdown_simple("Hola <b>!\n\n- [Tickantel](https://tickantel.com.uy), **ticketera**\n- Otra\n\nChau,\nDaniela")
    assert "<p>Hola &lt;b&gt;!</p>" in salida
    assert '<ul><li><a href="https://tickantel.com.uy">Tickantel</a>, <strong>ticketera</strong></li><li>Otra</li></ul>' in salida
    assert "<p>Chau,<br>Daniela</p>" in salida


def test_markdown_cada_pregunta_es_desplegable():
    from cartelera.sitio.generar import markdown_simple
    salida = str(markdown_simple("Hola\n\n# ¿Qué es?\n\nUn sitio.\n\n# ¿Cómo?\n\nAsí.\n\n---\n\nChau"))
    assert salida.count('<details class="pregunta" open><summary><h2>') == 2
    assert salida.index("<p>Hola</p>") < salida.index("<details")  # la presentación queda afuera
    assert salida.rstrip().endswith("</details>\n<p>Chau</p>")  # la despedida, después de "---", también


def test_markdown_no_deja_pasar_enlaces_que_no_son_web():
    from cartelera.sitio.generar import markdown_simple
    salida = markdown_simple("[malo](javascript:alert(1)) [bueno](https://x.uy) [interno](que-es.html) [mail](mailto:a@b.uy)")
    assert "javascript" not in salida.split("[malo]")[0] and 'href="javascript' not in salida
    assert 'href="https://x.uy"' in salida and 'href="que-es.html"' in salida and 'href="mailto:a@b.uy"' in salida


def test_los_enlaces_de_las_fuentes_tienen_que_ser_web():
    import pytest
    from pydantic import ValidationError
    from cartelera.modelo import Entrada, LugarCrudo, EventoCrudo
    with pytest.raises(ValidationError):
        Entrada(url="javascript:alert(1)", via="x")
    evento = EventoCrudo(fuente="x", id_externo="1", url="https://x.uy/1", titulo="T", lugar=LugarCrudo(nombre="L"),
                         funciones=[], imagen_url="data:image/svg+xml,<svg onload=alert(1)>")
    assert evento.imagen_url is None



def test_rock_y_pop_va_con_otros_en_los_generos():
    from cartelera.sitio.generar import datos_para_el_navegador
    base = {"titulo": "X", "lugar_id": "l", "fuentes": [{"url": "https://x.uy"}], "funciones": [{"inicio": "2026-11-01T20:00:00-03:00"}]}
    eventos = [dict(base, id="1", categoria="musica", subcategoria="rock_pop"), dict(base, id="2", categoria="musica", subcategoria="clasica")]
    datos = datos_para_el_navegador(eventos, {"l": {"nombre": "L"}}, [])
    assert [e["sub"] for e in datos["eventos"]] == [None, "clasica"]
    assert datos["subcategoriasOtros"]["musica"] == "Rock, pop y otros"


def test_un_solo_enlace_y_nunca_la_cartelera():
    from cartelera.sitio.generar import entrada_principal, promos_ordenadas
    fuentes = [{"fuente": "cartelera_mvd", "url": "https://cartelera.montevideo.com.uy/x"}]
    evento = {"fuentes": fuentes, "entradas": [
        {"via": "cartelera_mvd", "url": "https://cartelera.montevideo.com.uy/x"},
        {"via": "solis", "url": "https://teatrosolis.org.uy/x"},
        {"via": "tickantel", "url": "https://tickantel.com.uy/x"},
        {"via": "redtickets", "url": "https://redtickets.uy/y"},
    ]}
    assert entrada_principal(evento)["via"] == "tickantel"  # la ticketera, aunque la sala venga antes
    assert entrada_principal({"fuentes": fuentes, "entradas": evento["entradas"][:2]})["via"] == "solis"
    assert entrada_principal({"fuentes": fuentes, "entradas": evento["entradas"][:1]}) is None
    promos = promos_ordenadas({"beneficios": [{"programa": "Otras promos"}, {"programa": "la diaria"}]})
    assert [p["programa"] for p in promos] == ["la diaria", "Otras promos"]


def test_periodo_de_una_exposicion():
    from datetime import date, timedelta
    from cartelera.sitio.generar import periodo_muestra
    hoy, despues = date.today().isoformat(), (date.today() + timedelta(days=28)).isoformat()
    assert periodo_muestra({"funciones": [{"inicio": hoy + "T00:00:00-03:00"}], "hasta": "2027-02-28"}) == "Hasta el 28 feb 2027"
    assert periodo_muestra({"funciones": [{"inicio": hoy + "T00:00:00-03:00"}], "hasta": None}) == "En exhibición"
    assert periodo_muestra({"funciones": [{"inicio": despues + "T00:00:00-03:00"}], "hasta": None}).startswith("Desde el ")
