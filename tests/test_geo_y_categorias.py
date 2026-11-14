import pytest

from cartelera.categorias import clasificar, es_deporte, esta_cancelado
from cartelera.geo import en_montevideo


@pytest.mark.parametrize("lugar, lat, lon, esperado", [
    ("El Galpón", -34.90403, -56.181082, True),
    ("Teatro Solís", -34.90786, -56.20101, True),
    ("Carrasco", -34.885, -56.05, True),
    ("Colón", -34.80, -56.22, True),
    ("Las Piedras", -34.727, -56.219, False),
    ("La Paz", -34.761, -56.224, False),
    ("Aeropuerto de Carrasco", -34.838, -56.03, False),
    ("Colonia del Sacramento", -34.47, -57.85, False),
    ("Sin coordenadas", None, None, True),
])
def test_en_montevideo(lugar, lat, lon, esperado):
    assert en_montevideo(lat, lon) is esperado, lugar


@pytest.mark.parametrize("texto, categoria", [
    ("Rasgar la tierra, obra de teatro", "teatro"),
    ("Orquesta Filarmónica de Montevideo", "musica"),
    ("Ballet Nacional del Sodre", "danza"),
    ("Murga Agarrate Catalina", "carnaval"),
    ("Coronel", "otros"),  # "coro" no tiene que matchear dentro de otra palabra
])
def test_clasificar(texto, categoria):
    assert clasificar(texto) == categoria


def test_es_deporte():
    assert es_deporte("Lub Urunday vs Larrañaga")
    assert not es_deporte("La Vela Puerca")


def test_esta_cancelado():
    assert esta_cancelado("Zarzuela - La del Manojo de rosas - CANCELADO")
    assert esta_cancelado("Show suspendido")
    assert not esta_cancelado("Florencia Núñez - REPROGRAMADO")


def test_una_esquina_o_una_sala_no_es_otra_ciudad():
    from cartelera.geo import menciona_otra_ciudad
    assert menciona_otra_ciudad("Harlem Globetrotters – Durazno")
    assert menciona_otra_ciudad("No Te Va Gustar en Salto")
    assert not menciona_otra_ciudad("GUTIÉRREZ RUIZ 1111 esq. DURAZNO")
    assert not menciona_otra_ciudad("Universidad Católica del Uruguay (UCU) – Auditorio San José")
    assert not menciona_otra_ciudad("Soriano y Colonia")


def test_la_direccion_sin_la_esquina():
    from cartelera.geocodificar import sin_esquina
    assert sin_esquina("GUTIÉRREZ RUIZ 1111 esq. DURAZNO") == "GUTIÉRREZ RUIZ 1111"
    assert sin_esquina("Durazno 895 y Convención") == "Durazno 895"
    assert sin_esquina("Av. 18 de Julio 1249 esq. Yí") == "Avenida 18 de Julio 1249"
    assert sin_esquina("Soriano 1236") is None  # no hay nada que sacar
    assert sin_esquina("Gral. Flores y Domingo Aramburú") is None  # sin número, la esquina es todo lo que hay


def test_las_esquinas_sin_numero_de_puerta():
    from cartelera.geocodificar import calles_del_cruce

    assert calles_del_cruce("Bacacay y Buenos Aires") == ("Bacacay", "Buenos Aires")
    assert calles_del_cruce("Av. Agraciada esquina Gral. Fausto Aguilar") == ("Agraciada", "Fausto Aguilar")
    assert calles_del_cruce("21 de Setiembre y Gonzalo Ramírez") == ("21 de Setiembre", "Gonzalo Ramírez")
    # Con número de puerta lo busca Nominatim; un nombre de sala no es una esquina.
    assert calles_del_cruce("Soriano 1236 y Andes") is None
    assert calles_del_cruce("Teatro Solís") is None


def test_un_paseo_musical_es_un_recorrido():
    from cartelera.etiquetas import RECORRIDO_EN_TEXTO
    from cartelera.geo import sin_tildes

    assert RECORRIDO_EN_TEXTO.search(sin_tildes("Sumergite en un paseo musical inmersivo por la ciudad, recorriendo barrios"))
    # Una muestra que ofrece visitas guiadas sigue siendo una muestra.
    assert not RECORRIDO_EN_TEXTO.search(sin_tildes("La exposición cuenta con visitas guiadas los sábados"))
