from datetime import timedelta

from cartelera.scrapers import sodre

ITEM = {
    "start": "2026-12-10T20:00:00", "end": "2026-12-10T22:01:00", "title": "El Cascanueces",
    "url": "https://sodre.gub.uy/espectaculos/el-cascanueces/",
    "extendedProps": {
        "id": 11000, "foto_miniatura": "https://sodre.gub.uy/x.png", "resumen": "El clásico navideño",
        "enlace_de_compra": "https://tickantel.com.uy/ng/espectaculo/40021999/bns-el-cascanueces",
        "elencoEstablesData": [{"id": 22, "name": "Ballet Nacional"}],
    },
}


def test_arma_el_evento_con_fin_elenco_y_enlace_a_tickantel(ahora):
    evento = sodre.armar_evento([ITEM], "Auditorio Nacional Adela Reta", ahora)
    assert (evento.categoria, evento.categoria_segura) == ("danza", True)
    assert evento.productor == "Ballet Nacional del Sodre"
    assert evento.funciones[0].fin.isoformat() == "2026-12-10T22:01:00-03:00"
    assert evento.enlaces == [ITEM["extendedProps"]["enlace_de_compra"]]
    assert evento.entradas[0].via == "tickantel"


def test_descarta_funciones_pasadas_y_sin_fecha(ahora):
    pasada = {**ITEM, "start": (ahora - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")}
    sin_fecha = {**ITEM, "start": None}
    assert sodre.funciones_del_calendario([ITEM, pasada, sin_fecha], ahora) == {11000: [ITEM]}
