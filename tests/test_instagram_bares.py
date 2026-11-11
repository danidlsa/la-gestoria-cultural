import io
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx
from PIL import Image

from cartelera.scrapers import instagram_bares as ig

MVD = ZoneInfo("America/Montevideo")
AHORA = datetime(2026, 11, 10, 13, 0, tzinfo=MVD)


def funciones(texto, publicado=AHORA, ahora=AHORA):
    return [f.strftime("%d/%m %H:%M") for f in ig.leer_funciones(texto, publicado, ahora)]


def test_dia_y_hora_en_varias_formas():
    assert funciones("Jueves 12 y viernes 13 de noviembre\n21:30 h · Entrada $300") == ["12/11 21:30", "13/11 21:30"]
    assert funciones("Agenda:\nMiércoles 11 – Stand up 21h\nViernes 13 – Banda 23 hs") == ["11/11 21:00", "13/11 23:00"]
    assert funciones("Tocamos el 20/11 a las 22") == ["20/11 22:00"]
    assert funciones("HOY fiesta de disfraces a las 23") == ["10/11 23:00"]
    publicado = datetime(2026, 10, 24, 15, 0, tzinfo=MVD)
    assert funciones("Lunes otra vez. Presentación del libro, a las 19.30 h", publicado, publicado) == ["26/10 19:30"]


def test_la_hora_del_show_y_la_madrugada():
    assert funciones("Este viernes en vivo. Puerta 21 hs, show 22 hs") == ["13/11 22:00"]
    assert funciones("Sábado 14 – DJ set 00:30") == ["15/11 00:30"]  # la madrugada del domingo


def test_lo_que_no_es_un_evento():
    assert funciones("Lunes a viernes desde las 18h\nSábados desde las 20h") == []  # horario del bar
    assert funciones("Todos los jueves karaoke desde las 21h") == []
    assert funciones("Sorteo! Mañana anunciamos el ganador") == []  # sin hora
    assert funciones("Cerramos del 20/12 al 5/1") == []
    assert funciones("Jueves 5 de noviembre a las 21") == []  # ya pasó
    assert funciones("Viernes 13 – a las 5") == []  # a las 5 de la mañana: seguro es otra cosa
    assert funciones("Johnnie Walker te invita un trago hasta las 21 hs. Viernes 13, desde las 22") == ["13/11 22:00"]


def test_titulo_sin_adornos():
    assert ig.titulo_de("🎷 JAZZ EN EL BAR 🎷\nJueves 12", "bar") == "JAZZ EN EL BAR"
    assert ig.titulo_de("#jazz @alguien\n✨✨\nNoche de tango", "bar") == "Noche de tango"
    assert ig.titulo_de("🔥🔥", "Bar X") == "En Bar X"


def test_las_casillas_del_aviso():
    cuerpo = (
        "- [x] **Jazz en el bar** · Bar · jue 12/11 21:30 · [ver el post](https://x) <!-- ig:bar-1 -->\n"
        "  > texto\n"
        "- [ ] **Otra cosa** · Bar · vie 13/11 22:00 · [ver el post](https://y) <!-- ig:bar-2 -->\n"
        "- [X] **Título corregido a mano** · Bar · sáb 14/11 21:00 · [ver el post](https://z) <!-- ig:bar-3 -->\n"
    )
    aprobados, avisados = ig.leer_casillas([cuerpo])
    assert aprobados == {"bar-1": "Jazz en el bar", "bar-3": "Título corregido a mano"}
    assert avisados == {"bar-1", "bar-2", "bar-3"}
    # Lo que escribe el aviso se puede volver a leer.
    b = {"id": "bar-9", "titulo": "Show **con** asteriscos", "lugar": "Bar", "texto": "algo",
         "funciones": [{"inicio": "2026-11-12T21:30:00-03:00", "sin_hora": False}], "url": "https://www.instagram.com/p/1/", "usuario": "bar"}
    renglon = ig.renglon_del_borrador(b).replace("- [ ]", "- [x]")
    assert ig.leer_casillas([renglon])[0] == {"bar-9": "Show con asteriscos"}


def _jpeg():
    salida = io.BytesIO()
    Image.new("RGB", (40, 40), "orange").save(salida, "JPEG")
    return salida.getvalue()


def test_una_corrida(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bares.toml").write_text('[[bar]]\nusuario = "elbar"\n\n[[bar]]\nusuario = "personal"\n')
    monkeypatch.setattr(ig, "CONFIG", tmp_path / "bares.toml")
    monkeypatch.setenv("INSTAGRAM_TOKEN", "clave-de-prueba")
    posts = [
        {"id": "1", "caption": "🎷 Jazz en el bar\nJueves 12, 21:30 h. Entrada $300", "media_type": "IMAGE",
         "media_url": "https://cdn.example/1.jpg", "permalink": "https://www.instagram.com/p/1/",
         "timestamp": "2026-11-09T15:00:00+0000"},
        {"id": "2", "caption": "Abrimos de lunes a viernes desde las 18h", "media_type": "IMAGE",
         "media_url": "https://cdn.example/2.jpg", "permalink": "https://www.instagram.com/p/2/",
         "timestamp": "2026-11-09T15:00:00+0000"},
    ]
    claves_vistas = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        claves_vistas.append((pedido.url.host, pedido.headers.get("authorization")))
        if pedido.url.host == "cdn.example":
            return httpx.Response(200, content=_jpeg())
        if pedido.url.path.endswith("/me"):
            return httpx.Response(200, json={"instagram_business_account": {"id": "999"}})
        if "personal" in pedido.url.params["fields"]:
            return httpx.Response(400, json={"error": {"message": "Invalid user id", "code": 110}})
        return httpx.Response(200, json={"business_discovery": {"name": "El Bar", "media": {"data": posts}}})

    monkeypatch.setattr(ig, "TRANSPORTE", httpx.MockTransport(responder))

    # Primera corrida: nada tildado todavía. Queda un borrador (el horario del bar no) y no se publica nada.
    monkeypatch.setattr(ig, "avisos_en_github", lambda: [])
    eventos, errores = ig.scrapear(None, AHORA)
    assert eventos == [] and errores == []
    borradores = json.loads(ig.BORRADORES.read_text())
    assert [b["titulo"] for b in borradores] == ["Jazz en el bar"]

    # Se tilda en el aviso (con otro título): en la corrida siguiente se publica, con la imagen guardada aparte.
    renglon = ig.renglon_del_borrador(borradores[0]).replace("- [ ]", "- [x]").replace("Jazz en el bar", "Jazz con Trío X")
    monkeypatch.setattr(ig, "avisos_en_github", lambda: [{"number": 1, "state": "OPEN", "body": renglon}])
    eventos, errores = ig.scrapear(None, AHORA)
    assert errores == []
    (evento,) = eventos
    assert evento.titulo == "Jazz con Trío X" and evento.lugar.nombre == "El Bar"
    assert evento.entradas[0].via == "instagram" and evento.precio.desde == 300
    assert evento.imagen_url.startswith("https://lagestoriacultural.uy/afiches/instagram/")
    assert len(list(ig.DIR_AFICHES.glob("*.jpg"))) == 1
    # La clave va solo a la API de Meta, nunca al servidor de imágenes.
    assert ("cdn.example", None) in claves_vistas
    assert all(clave == "Bearer clave-de-prueba" for host, clave in claves_vistas if host == "graph.facebook.com")

    # Si se saca el tilde, se va (y su imagen también).
    monkeypatch.setattr(ig, "avisos_en_github", lambda: [{"number": 1, "state": "OPEN", "body": renglon.replace("[x]", "[ ]")}])
    eventos, _ = ig.scrapear(None, AHORA)
    assert eventos == [] and not list(ig.DIR_AFICHES.glob("*.jpg"))


def test_sin_clave_la_corrida_falla_y_queda_lo_anterior(monkeypatch):
    import pytest
    monkeypatch.delenv("INSTAGRAM_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        ig.scrapear(None, AHORA)


def test_el_aviso_solo_trae_lo_nuevo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    b = {"id": "bar-1", "usuario": "bar", "titulo": "Jazz", "lugar": "Bar", "texto": "Jueves 12 21h",
         "funciones": [{"inicio": "2026-11-12T21:00:00-03:00", "sin_hora": False}], "url": "https://www.instagram.com/p/1/"}
    ig.guardar_borradores({"bar-1": b, "bar-2": {**b, "id": "bar-2", "titulo": "Otro"}})
    ya_avisado = ig.renglon_del_borrador(b)
    monkeypatch.setattr(ig, "avisos_en_github", lambda: [{"number": 3, "state": "OPEN", "body": ya_avisado}])
    llamados = []
    monkeypatch.setattr(ig.subprocess, "run", lambda comando, **_: llamados.append(comando))
    monkeypatch.setenv("GH_REPO", "duena/repo")
    nuevos = ig.avisar(en_github=True, ahora=AHORA)
    assert [n["id"] for n in nuevos] == ["bar-2"]
    (crear,) = [c for c in llamados if c[:3] == ["gh", "issue", "create"]]
    assert "Otro" in crear[crear.index("--body") + 1] and crear[crear.index("--assignee") + 1] == "duena"
    assert not [c for c in llamados if c[:3] == ["gh", "issue", "close"]]  # sigue vigente


def test_con_una_clave_de_usuario_tambien_encuentra_la_cuenta():
    def responder(pedido: httpx.Request) -> httpx.Response:
        if pedido.url.path.endswith("/me"):
            return httpx.Response(400, json={"error": {"message": "nonexisting field (instagram_business_account)", "code": 100}})
        return httpx.Response(200, json={"data": {"granular_scopes": [
            {"scope": "pages_show_list", "target_ids": ["111"]}, {"scope": "instagram_basic", "target_ids": ["999"]}]}})
    with httpx.Client(transport=httpx.MockTransport(responder)) as http:
        assert ig.cuenta_de_la_gestoria(http, "clave") == "999"


def test_el_mismo_evento_en_varios_posts_es_un_borrador_y_el_lugar_sale_del_pin():
    cuenta = {"usuario": "mbc"}
    perfil = {"name": "Montevideo Beer Company"}
    def post(i, dia, texto):
        return {"id": str(i), "caption": texto, "media_type": "IMAGE", "media_url": f"https://cdn/{i}.jpg",
                "permalink": f"https://www.instagram.com/p/{i}/", "timestamp": f"2026-11-0{dia}T15:00:00+0000"}
    (a,) = ig.borradores_del_post(post(1, 3, "Festejamos 10 años!\n📅 13 de noviembre 21 hs\n📍 Museo Oceanográfico 🥃 trago"), cuenta, perfil, AHORA)
    (b,) = ig.borradores_del_post(post(2, 8, "Se suma otra banda!\n13 de noviembre, 21 hs\n📍Museo Oceanográfico"), cuenta, perfil, AHORA)
    assert a["id"] == b["id"] == "mbc-20261113"
    (sin_pin,) = ig.borradores_del_post(post(5, 9, "Una década de planes merecía una noche así, con todo\n13 de noviembre 21 hs"), cuenta, perfil, AHORA)
    junto = ig.juntar(ig.juntar(a, b), sin_pin)
    assert junto["titulo"] == "Montevideo Beer Company: Se suma otra banda" and len(junto["posts"]) == 3  # el título más corto
    assert junto["url"].endswith("/5/")  # el enlace principal, el post más reciente
    assert junto["lugar"] == "Museo Oceanográfico" and junto["barrio"] is None  # aunque el último post no traiga 📍
    renglon = ig.renglon_del_borrador(junto)
    assert "(y 2 posts más sobre lo mismo)" in renglon and "`mbc`" in renglon and "@mbc" not in renglon
    # Un 📍 que nombra al mismo bar deja el bar, con la dirección si la trae.
    (c,) = ig.borradores_del_post(post(3, 8, "Show 20/11 21h\n📍La Cretina, Soriano 1236"), {"usuario": "lacretinacasa", "nombre": "La Cretina"}, {}, AHORA)
    assert (c["lugar"], c["direccion"]) == ("La Cretina", "Soriano 1236")
    # Dos horas para el mismo día: queda una sola función.
    (d,) = ig.borradores_del_post(post(4, 8, "El domingo 6 de diciembre, a las 20 horas.\n🗓️ Domingo 6 de diciembre\n🎶 19:00 h"), cuenta, perfil, AHORA)
    assert len(d["funciones"]) == 1


SHANNON_MES = """Calendario de espectáculos de Noviembre 2026

Miércoles 4: OPEN MIC
Jueves 5: A CONFIRMAR
Miércoles 11: OPEN MIC
Jueves 12: SPAGUETTI WESTERN
Viernes 13: PROYECTO OLDIES
Club Shannon: VOLDCAST, ATROPELLO y SABOTAJE
Sábado 14: MORRIGAN'S
Jueves 26: A CONFIRMAR"""

SHANNON_SEMANA = """Estimados, les presentamos el calendario de espectáculos de la semana!!!!!

Miércoles 11/Noviembre:
OPEN MIC NIGHT - 4ta temporada
Bienvenidos al primer Open Mic de Uruguay. Participa, compartí tu arte.
Entrada libre 21:30hrs

Viernes 13/Noviembre:
PROYECTO OLDIES
Rock - 22 hs
Cubierto artístico $350"""


def _post(i, texto, dia="2026-11-04"):
    return {"id": str(i), "caption": texto, "media_type": "IMAGE", "media_url": f"https://cdn/{i}.jpg",
            "permalink": f"https://www.instagram.com/p/{i}/", "timestamp": f"{dia}T15:00:00+0000"}


def test_una_agenda_es_un_borrador_por_dia():
    cuenta, perfil = {"usuario": "theshannonuy"}, {"name": "The Shannon"}
    mes = ig.borradores_del_post(_post(1, SHANNON_MES), cuenta, perfil, AHORA)
    assert [(b["titulo"], b["funciones"][0]["sin_hora"]) for b in mes] == [
        ("The Shannon: OPEN MIC", True), ("The Shannon: SPAGUETTI WESTERN", True), ("The Shannon: PROYECTO OLDIES", True),
        ("The Shannon: MORRIGAN'S", True)]
    assert "VOLDCAST" in mes[2]["extracto"]  # lo de la otra sala del mismo día va en la descripción
    semana = ig.borradores_del_post(_post(2, SHANNON_SEMANA, "2026-11-09"), cuenta, perfil, AHORA)
    assert [(b["titulo"], b["funciones"][0]["inicio"][11:16]) for b in semana] == [
        ("The Shannon: OPEN MIC NIGHT", "21:30"), ("The Shannon: PROYECTO OLDIES", "22:00")]
    # La agenda del mes y la de la semana hablan del mismo día: queda uno, con la hora de la de la semana.
    assert mes[2]["id"] == semana[1]["id"] == "theshannonuy-20261113"
    junto = ig.juntar(mes[2], semana[1])
    assert junto["funciones"] == [{"inicio": "2026-11-13T22:00:00-03:00", "sin_hora": False}]
    assert "(la hora está en el post)" in ig.renglon_del_borrador(mes[0])
    evento = ig.evento_de(semana[1], AHORA)
    assert evento.precio.desde == 350 and evento.titulo == "The Shannon: PROYECTO OLDIES"


def test_la_agenda_del_mingus():
    texto = ("Musica y toques de esta semana en El Mingus:\n\nMartes 10 de noviembre: Martes de Jazz (todos los martes)\n\n"
             "Miércoles 11 de Noviembre: Jazz & Bossa\n\nSábado 14 de noviembre (al mediodía): Piano Bar \n\n"
             "Reservá tu mesa via Whatsapp al 093 651 305.")
    lista = ig.borradores_del_post(_post(1, texto, "2026-11-09"), {"usuario": "el.mingus"}, {"name": "El Mingus"}, AHORA)
    assert [(b["titulo"], b["funciones"][0]["sin_hora"]) for b in lista] == [
        ("El Mingus: Martes de Jazz", True), ("El Mingus: Jazz & Bossa", True), ("El Mingus: Piano Bar", False)]
    assert lista[2]["funciones"][0]["inicio"][11:16] == "12:00"  # al mediodía


def test_un_dia_con_numero_sin_hora_entra_como_hora_a_confirmar():
    (b,) = ig.borradores_del_post(_post(1, "Cumplimos 12 años. El 29 de noviembre nos vemos en la calle", "2026-11-09"),
                                  {"usuario": "bar"}, {}, AHORA)
    assert b["funciones"] == [{"inicio": "2026-11-29T00:00:00-03:00", "sin_hora": True}]
    # Pero "el viernes" sin hora, o un período, no.
    assert ig.borradores_del_post(_post(2, "Este viernes nos vemos", "2026-11-09"), {"usuario": "bar"}, {}, AHORA) == []
    assert ig.borradores_del_post(_post(3, "Cerramos del 20/12 al 5/1", "2026-11-09"), {"usuario": "bar"}, {}, AHORA) == []



def test_lo_que_mostraron_los_posts_reales():
    cuenta = {"usuario": "bar"}
    # Un ciclo: "Martes de noviembre / 21:00 h" son todos los martes que quedan del mes.
    (taberna,) = ig.borradores_del_post(_post(1, "Se acerca el cierre pero aún quedan martes y mucha música.\n\n"
                                                 "Martes de noviembre / 21:00 h.\nEntrada libre.", "2026-11-09"), cuenta, {}, AHORA)
    assert [f["inicio"][:16] for f in taberna["funciones"]] == ["2026-11-10T21:00", "2026-11-17T21:00", "2026-11-24T21:00"]
    # Un sorteo no es un evento, aunque diga "jueves 12/11".
    sorteo = "Sorteamos una mesa para 10 personas.\n\nAnunciamos ganador el jueves 12/11 👀\n\nVálido hasta el 31/12/2026."
    assert ig.borradores_del_post(_post(2, sorteo, "2026-11-09"), cuenta, {}, AHORA) == []
    # Títulos sin la fecha, sin propaganda y con el nombre de abajo si es corto.
    assert ig.titulo_de("Este miércoles en Noches De Ensayos Abiertos\n\nLali Gaspari\n\nMúsica y compositora.", "x") == \
        "Noches De Ensayos Abiertos · Lali Gaspari"
    assert ig.titulo_de("FERIADO + MONKELIS I 2 DE DICIEMBRE EN LA CRETINA\n\n@feriado.uy se presenta", "x") == "FERIADO + MONKELIS"
    assert ig.titulo_de("🍻🎧 ¡ENTRADA GRATIS! INSCRIBITE EN EL LINK DE NUESTRA BIO.\nLa noche tiene dos lados", "x") == \
        "La noche tiene dos lados"
    assert ig.titulo_de("Este viernes 13 de noviembre celebramos la Noche de las Librerías en Mercado Ferrando", "x") == \
        "Celebramos la Noche de las Librerías en Mercado Ferrando"
    # Dos horas para el mismo día: la que aparece primero (el afiche de Mané dice 20 h).
    mane = ("El próximo domingo 6 de diciembre, a las 20 horas, Mané abre las puertas.\n\n"
            "📍 LA CRETINA\n🗓️ Domingo 6 de diciembre\n🎶 19:00 h")
    (b,) = ig.borradores_del_post(_post(3, mane), {"usuario": "lacretinacasa", "nombre": "La Cretina"}, {}, AHORA)
    assert b["funciones"][0]["inicio"][11:16] == "20:00"
    # El ciclo del mes y el post de un martes se juntan sin perder días.
    (un_martes,) = ig.borradores_del_post(_post(4, "Qué martes se viene\nMartes 10 de noviembre / 21:00 h.", "2026-11-10"), cuenta, {}, AHORA)
    assert len(ig.juntar(taberna, un_martes)["funciones"]) == 3


def test_lo_que_ya_no_sale_se_va_salvo_lo_aprobado(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bares.toml").write_text('[[bar]]\nusuario = "elbar"\n')
    monkeypatch.setattr(ig, "CONFIG", tmp_path / "bares.toml")
    monkeypatch.setenv("INSTAGRAM_TOKEN", "x")
    viejo = {"id": "elbar-20261120", "usuario": "elbar", "titulo": "Sorteo", "lugar": "Bar", "texto": "t",
             "funciones": [{"inicio": "2026-11-20T21:00:00-03:00", "sin_hora": False}], "url": "https://www.instagram.com/p/9/"}
    ig.guardar_borradores({"elbar-20261120": viejo, "elbar-20261125": {**viejo, "id": "elbar-20261125", "aprobado": True,
                           "funciones": [{"inicio": "2026-11-25T21:00:00-03:00", "sin_hora": False}]}})

    def responder(pedido):
        if pedido.url.path.endswith("/me"):
            return httpx.Response(200, json={"instagram_business_account": {"id": "1"}})
        return httpx.Response(200, json={"business_discovery": {"name": "Bar", "media": {"data": []}}})

    monkeypatch.setattr(ig, "TRANSPORTE", httpx.MockTransport(responder))
    monkeypatch.setattr(ig, "avisos_en_github", lambda: None)  # sin GitHub: valen las decisiones guardadas
    eventos, _ = ig.scrapear(None, AHORA)
    assert set(ig.cargar_borradores()) == {"elbar-20261125"} and [e.id_externo for e in eventos] == ["elbar-20261125"]



def test_el_nombre_del_bar_en_el_titulo():
    assert ig.nombre_corto("MBC | MONTEVIDEO BEER COMPANY") == "MBC"
    assert ig.nombre_corto("Brecha Bar y Café 🏳️‍🌈") == "Brecha Bar y Café"
    assert ig.nombre_corto("INMIGRANTES") == "Inmigrantes"
    assert ig.con_el_bar("SPAGUETTI WESTERN", "The Shannon") == "The Shannon: SPAGUETTI WESTERN"
    # Si el título ya lo nombra, no se repite.
    assert ig.con_el_bar("Celebramos la Noche de las Librerías en Mercado Ferrando", "Mercado Ferrando") == \
        "Celebramos la Noche de las Librerías en Mercado Ferrando"
    # El nombre corto de la lista de bares gana sobre el del perfil.
    (b,) = ig.borradores_del_post(_post(1, "Jueves 12: SPAGUETTI WESTERN 22 hs", "2026-11-09"),
                                  {"usuario": "theshannonuy", "corto": "The Shannon"}, {"name": "The Shannon irish pub"}, AHORA)
    assert b["titulo"] == "The Shannon: SPAGUETTI WESTERN" and b["lugar"] == "The Shannon irish pub"


MAMBO = """⚠️ Esta noche: MAMBO

🎭✨ ¡MAMBO!

Un retrato contemporáneo, mordaz, profundamente humano y de humor corrosivo.

Elenco: amaral2435 y laleochavarria
Dirección: alfredo.goldstein

🗓️ Funciones:
Noviembre:
miércoles 11 y 18 | lunes 30 (20:30 hs) 🗓️🕒
Diciembre:
lunes 7, 14 y 21 (20:30 hs) 🗓️🕒

📷 alejandropersichetti
Produce: weproducciones"""


def test_una_obra_con_varias_funciones_es_un_borrador():
    ahora = datetime(2026, 11, 11, 10, 0, tzinfo=MVD)
    (b,) = ig.borradores_del_post(_post(1, MAMBO, "2026-11-11"), {"usuario": "lacretinacasa", "corto": "La Cretina"}, {}, ahora)
    assert b["titulo"] == "La Cretina: MAMBO"
    assert [f["inicio"][:16] for f in b["funciones"]] == [
        "2026-11-11T20:30", "2026-11-18T20:30", "2026-11-30T20:30", "2026-12-07T20:30", "2026-12-14T20:30", "2026-12-21T20:30"]
    assert ig.fechas_explicitas("13, 14 y 15 de noviembre", AHORA.date()) == [
        (date(2026, 11, 13), True), (date(2026, 11, 14), True), (date(2026, 11, 15), True)]


def test_el_borrador_no_cambia_de_identificador_cuando_pasa_su_primer_dia():
    texto = "Se acerca el cierre pero aún quedan martes y mucha música.\n\nMartes de noviembre / 21:00 h."
    ayer = ig.borradores_del_post(_post(1, texto, "2026-11-09"), {"usuario": "bar"}, {}, datetime(2026, 11, 10, 12, tzinfo=MVD))
    hoy = ig.borradores_del_post(_post(1, texto, "2026-11-09"), {"usuario": "bar"}, {}, datetime(2026, 11, 11, 12, tzinfo=MVD))
    assert ayer[0]["id"] == hoy[0]["id"] == "bar-20261110"
    # El día que ya pasó no se publica.
    evento = ig.evento_de(hoy[0], datetime(2026, 11, 11, 12, tzinfo=MVD))
    assert [f.inicio.day for f in evento.funciones] == [17, 24]


def test_las_coordenadas_de_la_lista_de_bares():
    cuenta = {"usuario": "latabernadebrecha", "direccion": "Durazno y Jackson", "lat": -34.909634, "lon": -56.172902}
    (b,) = ig.borradores_del_post(_post(1, "Martes 17 de noviembre 21 h", "2026-11-11"), cuenta, {"name": "La Taberna de Brecha"}, AHORA)
    lugar = ig.evento_de(b, AHORA).lugar
    assert (lugar.direccion, lugar.lat, lugar.lon) == ("Durazno y Jackson", -34.909634, -56.172902)



def test_dos_posts_de_la_misma_obra_son_un_borrador():
    estreno = ("🎭 MAMBO | De Miguel Morillo\n\n📅 ESTRENO: Miércoles 21 de octubre – 20:30 hs\n📍 La Cretina (Soriano 1236)\n\n"
               "🗓️ FUNCIONES (20:30 hs):\n▪️ Octubre: Miércoles 21 y 28\n▪️ Noviembre: Miércoles 11 y 18 | Lunes 30\n"
               "▪️ Diciembre: Lunes 7, 14 y 21\n\n🎫 Venta de entradas: Red Tickets 🎟️")
    cuenta = {"usuario": "lacretinacasa", "corto": "La Cretina"}
    ahora = datetime(2026, 11, 11, 10, 0, tzinfo=MVD)
    (viejo,) = ig.borradores_del_post(_post(1, estreno, "2026-10-10"), cuenta, {}, ahora)
    (nuevo,) = ig.borradores_del_post(_post(2, MAMBO, "2026-11-11"), cuenta, {}, ahora)
    assert viejo["titulo"] == nuevo["titulo"] == "La Cretina: MAMBO"
    assert viejo["id"] != nuevo["id"]
    (junto,) = ig.juntar_parecidos({viejo["id"]: viejo, nuevo["id"]: nuevo}).values()
    assert junto["id"] == viejo["id"] and len(junto["posts"]) == 2
    assert all(f["inicio"][11:16] == "20:30" for f in junto["funciones"])
