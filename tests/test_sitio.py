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

