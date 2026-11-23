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
    ("Desplazamiento: historias de amor, familia y barro", "otros"),  # "familia" sola no es infantil
    ("Cuentos para disfrutar en familia", "infantil"),
    ("Un espectáculo para toda la familia", "infantil"),
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


def test_los_plus_codes_se_pasan_a_coordenadas():
    from cartelera.geocodificar import plus_code

    # La Sala Hugo Balzo (Sodre, Andes y Mercedes): a unos metros de -34.9043, -56.1987.
    lat, lon = plus_code("3RW2+69X Estudio Auditorio del Sodre")
    assert abs(lat + 34.9043) < 0.001 and abs(lon + 56.1987) < 0.001
    assert plus_code("3RMJ+QG6, 11200 Montevideo, Departamento de Montevideo") is not None
    assert plus_code("Soriano 1236") is None


def test_el_titulo_dice_si_es_taller_o_feria():
    from cartelera.categorias import clasificar
    # El texto habla de una revista y de espectáculos en vivo, pero el título manda.
    assert clasificar("FAC: Laboratorio de escritura", "Fue directora editorial de la revista ARTE") == "taller"
    assert clasificar("Feria de emprendedores", "con espectáculos en vivo y food trucks") == "feria"
    assert clasificar("FERIADO + MONKELIS en La Cretina", "banda en vivo") == "musica"  # "feriado" no es feria
    # "revista" ya no es carnaval.
    assert clasificar("Presentación", "la revista Lento presenta su número 20") != "carnaval"


def test_una_calle_con_inicial_en_openstreetmap():
    import re
    from cartelera.geocodificar import _patron
    assert re.search(_patron("Aquiles Lanza"), "Aquiles R. Lanza", re.I)
    assert re.search(_patron("Aquiles Lanza"), "Aquiles Lanza", re.I)
    assert "(?:" not in _patron("Aquiles Lanza")  # Overpass no entiende esa sintaxis


def test_la_opera_prima_es_cine():
    texto = ("Festival Internacional Atlantidoc | Ciclo de cine. Perros. Ópera prima de Minutti y con el protagónico de "
             "Nestor Guzzini.")
    assert clasificar("Centro Cultural Terminal Goes: Festival Internacional Atlantidoc", texto) == "cine"
    assert clasificar("Gala de ópera", "Arias de Verdi y Puccini") == "musica"


def test_una_comida_no_es_un_evento_pero_una_cena_show_si():
    from cartelera.categorias import es_comida
    assert es_comida("Cena de Noche buena - Polo Bamba Skybar, piso 10")
    assert es_comida("Almuerzo buffet Navidad, Polo Bamba Skybar, piso 10")
    assert not es_comida("HUMORISIMAS CENA SHOW - GRAN REGRESO")
    assert not es_comida("LA DECANA - CENA SHOW BAILE en TEATRÓN")
    assert not es_comida("Cena show de tango")
