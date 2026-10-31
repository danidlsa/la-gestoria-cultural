from datetime import datetime, timedelta

from cartelera.modelo import Beneficio, Entrada, EventoCrudo, Funcion, LugarCrudo, Precio, ResultadoFuente
from cartelera.unificar import Catalogo, armar_cartelera, clave_de_url, separar_sala, titulo_comparable, titulos_parecidos

ALIAS = [{"id": "teatro-el-galpon", "nombre": "Teatro El Galpón", "alias": ["Teatro Galpón"]}]


def crudo(fuente, id_externo, titulo, lugar, inicio, **extra):
    datos = dict(
        fuente=fuente, id_externo=id_externo, url=f"https://{fuente}/{id_externo}", titulo=titulo,
        lugar=LugarCrudo(nombre=lugar, lat=-34.90403, lon=-56.181082),
        funciones=[Funcion(inicio=inicio)],
    )
    datos.update(extra)
    return EventoCrudo(**datos)


def resultado(fuente, eventos, ahora):
    return ResultadoFuente(fuente=fuente, corrida=ahora, ok=True, cantidad=len(eventos), eventos=eventos)


def test_une_el_mismo_evento_de_dos_ticketeras(ahora):
    funcion = ahora + timedelta(days=2)
    eventos, lugares, _ = armar_cartelera([
        resultado("redtickets", [crudo("redtickets", "1", "LA REBELIÓN DE LA CARNE (Sala Cero)", "Teatro El Galpón", funcion,
                                       categoria="teatro", categoria_segura=True,
                                       beneficios=[Beneficio(programa="la diaria", tipo="2x1", url="https://x")],
                                       precio=Precio(desde=650, hasta=650))], ahora),
        resultado("tickantel", [crudo("tickantel", "9", "La rebelión de la carne", "Teatro Galpón", funcion,
                                      precio=Precio(desde=600, hasta=600))], ahora),
    ], ALIAS, ahora)

    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.lugar_id == "teatro-el-galpon"
    assert evento.categoria == "teatro"
    assert evento.precio.desde == 600 and evento.precio.hasta == 650
    assert [b.programa for b in evento.beneficios] == ["la diaria"]
    assert {p.fuente for p in evento.fuentes} == {"redtickets", "tickantel"}
    assert [l.id for l in lugares] == ["teatro-el-galpon"]


def test_une_por_enlace_aunque_el_titulo_sea_distinto(ahora):
    funcion = ahora + timedelta(days=1)
    eventos, _, _ = armar_cartelera([
        resultado("redtickets", [crudo("redtickets", "34406", "Obra A", "Sala X", funcion)], ahora),
        resultado("ladiaria", [crudo("ladiaria", "obra-a", "Un título totalmente distinto", "Sala X", funcion,
                                     enlaces=["https://redtickets.uy/evento/OBRA-A/34406/"])], ahora),
    ], [], ahora)
    assert len(eventos) == 1


def test_no_une_eventos_distintos_en_la_misma_sala(ahora):
    funcion = ahora + timedelta(days=1)
    eventos, _, _ = armar_cartelera([
        resultado("redtickets", [crudo("redtickets", "1", "Hamlet", "Teatro El Galpón", funcion)], ahora),
        resultado("tickantel", [crudo("tickantel", "2", "Las troyanas", "Teatro El Galpón", funcion)], ahora),
    ], ALIAS, ahora)
    assert len(eventos) == 2


def test_descarta_lo_vencido(ahora):
    vencida = ahora - timedelta(days=1)
    futura = ahora + timedelta(days=1)
    evento_mixto = crudo("redtickets", "1", "Obra", "Sala", vencida)
    evento_mixto.funciones.append(Funcion(inicio=futura))
    eventos, _, _ = armar_cartelera([
        resultado("redtickets", [evento_mixto, crudo("redtickets", "2", "Otra", "Sala", vencida)], ahora),
    ], [], ahora)
    assert len(eventos) == 1
    assert [f.inicio for f in eventos[0].funciones] == [futura]


def test_agotada_solo_si_todas_las_fuentes_lo_dicen(ahora):
    inicio = ahora + timedelta(days=1)
    a = crudo("redtickets", "1", "Concierto", "Sala", inicio, funciones=[Funcion(inicio=inicio, agotada=True)])
    b = crudo("tickantel", "2", "Concierto", "Sala", inicio, funciones=[Funcion(inicio=inicio, agotada=False)])
    eventos, _, _ = armar_cartelera([resultado("redtickets", [a], ahora), resultado("tickantel", [b], ahora)], [], ahora)
    assert not eventos[0].funciones[0].agotada


def test_el_id_es_estable(ahora):
    inicio = ahora + timedelta(days=1)
    entrada = [resultado("redtickets", [crudo("redtickets", "1", "Obra", "Sala", inicio)], ahora)]
    primero, _, _ = armar_cartelera(entrada, [], ahora)
    segundo, _, _ = armar_cartelera(entrada, [], ahora + timedelta(hours=3))
    assert primero[0].id == segundo[0].id


def test_clave_de_url():
    assert clave_de_url("https://redtickets.uy/evento/COTI/32964/") == "redtickets:32964"
    assert clave_de_url("https://tickantel.com.uy/ng/espectaculo/alta-demanda/40021784/la-trampa") == "tickantel:40021784"
    assert clave_de_url("https://tickantel.com.uy/inicio/espectaculo/40021761/x") == "tickantel:40021761"
    assert clave_de_url("https://tickantel.com.uy/inicio/alta_demanda/40020997") == "tickantel:40020997"
    assert clave_de_url("https://tickantel.com.uy/inicio/espectaculo/40020784") == "tickantel:40020784"
    assert clave_de_url("https://otro.uy/x") is None


def test_titulo_comparable():
    assert titulo_comparable("LA REBELIÓN DE LA CARNE (Sala Cero)") == titulo_comparable("La rebelión de la carne")


def test_sin_coordenadas_entra_solo_si_la_sala_es_conocida(ahora):
    funcion = ahora + timedelta(days=1)
    conocida = crudo("redtickets", "1", "Obra", "Teatro El Galpón", funcion)
    sin_coordenadas = crudo("tickantel", "2", "Otra obra", "Teatro Galpón", funcion)
    sin_coordenadas.lugar = LugarCrudo(nombre="Teatro Galpón")
    del_interior = crudo("tickantel", "3", "Recital", "Liga de Fomento Atlántida", funcion)
    del_interior.lugar = LugarCrudo(nombre="Liga de Fomento Atlántida")
    eventos, _, _ = armar_cartelera([
        resultado("redtickets", [conocida], ahora), resultado("tickantel", [sin_coordenadas, del_interior], ahora),
    ], ALIAS, ahora)
    assert sorted(e.titulo for e in eventos) == ["Obra", "Otra obra"]


def test_titulos_parecidos():
    assert titulos_parecidos("LA REBELIÓN DE LA CARNE (Sala Cero)", "La rebelión de la carne")
    assert titulos_parecidos("Jaime Roos en concierto", "Jaime Roos")
    assert titulos_parecidos("No Te Va Gustar - Gira 2026", "No Te Va Gustar")
    assert not titulos_parecidos("Obra", "Otra obra")
    assert not titulos_parecidos("Hamlet", "Las troyanas")


def test_separar_sala():
    assert separar_sala("El Galpón - Sala Cero") == ("El Galpón", "Sala Cero")
    assert separar_sala("Teatro Stella D'Italia - La Gaviota") == ("Teatro Stella D'Italia - La Gaviota", None)


def test_reconoce_la_misma_sala_con_nombres_distintos():
    catalogo = Catalogo([])
    mandragora = catalogo.asignar("Teatro MANDRÁGORA Escuela de Artes", None, -34.89, -56.15)
    assert catalogo.asignar("Teatro Mandrágora", "Dr. Javier Barrios Amorín 1312", None, None) == mandragora
    esnade = catalogo.asignar("ESNADE (Escuela Nacional de Declamación)", None, None, None)
    assert catalogo.asignar("Escuela Nacional de Declamación - ESNADE", None, None, None) == esnade
    galpon = catalogo.asignar("Teatro El Galpón", None, -34.904, -56.181)
    assert catalogo.asignar("El Galpón - Sala Atahualpa", None, None, None) == galpon
    solis = catalogo.asignar("Teatro Solís", None, -34.907, -56.201)
    assert solis != galpon
    assert catalogo.asignar("Vieja Farmacia Solís", None, None, None) != solis
    assert catalogo.asignar("Sala Verdi", None, None, None) != catalogo.asignar("Sala Zitarrosa", None, None, None)


def test_no_repite_el_mismo_enlace_de_compra(ahora):
    funcion = ahora + timedelta(days=1)
    a = crudo("solis", "1", "El Teatro", "Teatro Solís", funcion,
              entradas=[Entrada(url="https://tickantel.com.uy/inicio/espectaculo/40021401/espectaculo/El%20Teatro?1", via="tickantel")],
              enlaces=["https://tickantel.com.uy/inicio/espectaculo/40021401/espectaculo/El%20Teatro?1"])
    b = crudo("tickantel", "40021401", "El Teatro", "Teatro Solís", funcion,
              url="https://tickantel.com.uy/ng/espectaculo/40021401/el-teatro",
              entradas=[Entrada(url="https://tickantel.com.uy/ng/espectaculo/40021401/el-teatro", via="tickantel")])
    eventos, _, _ = armar_cartelera([resultado("solis", [a], ahora), resultado("tickantel", [b], ahora)], [], ahora)
    assert len(eventos) == 1 and len(eventos[0].entradas) == 1


def test_una_actividad_en_varios_barrios_va_en_la_intendencia(ahora):
    from cartelera.geo import VARIOS_BARRIOS
    from cartelera.unificar import cargar_alias
    barrios = crudo("portal_im", "1", "Canto colectivo", VARIOS_BARRIOS, ahora + timedelta(days=2))
    barrios.lugar = LugarCrudo(nombre=VARIOS_BARRIOS)
    # Un evento que sí es en la Intendencia, a metros del punto: no se tiene que sumar a "Varios barrios".
    atrio = crudo("tickantel", "2", "Muestra en el Atrio", "Intendencia de Montevideo", ahora + timedelta(days=2))
    atrio.lugar = LugarCrudo(nombre="Intendencia de Montevideo", lat=-34.9066, lon=-56.1861)
    eventos, lugares, _ = armar_cartelera(
        [resultado("portal_im", [barrios], ahora), resultado("tickantel", [atrio], ahora)], cargar_alias(), ahora,
    )
    lugar_de = {e.titulo: e.lugar_id for e in eventos}
    assert lugar_de == {"Canto colectivo": "varios-barrios-de-montevideo", "Muestra en el Atrio": "intendencia-de-montevideo"}
    varios = next(l for l in lugares if l.id == "varios-barrios-de-montevideo")
    assert (round(varios.lat, 3), round(varios.lon, 3), varios.alias) == (-34.906, -56.185, [])
