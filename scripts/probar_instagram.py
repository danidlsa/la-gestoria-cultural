"""Prueba si la API oficial de Instagram (Business Discovery) anda con la cuenta de La Gestoría.

Uso (desde la carpeta del repo):

    uv run python scripts/probar_instagram.py               # prueba con una cuenta de ejemplo
    uv run python scripts/probar_instagram.py nombre_del_bar

Pide la clave de acceso (no se ve al pegarla) y no la guarda en ningún lado. La clave viaja en un encabezado, no en
la dirección, para que no quede en ningún registro. Ver docs/instagram-bares.md.

Prueba dos claves:
- la tuya (la de "usuario"), que es la que indica la documentación de Meta y vence a los 60 días;
- la de tu página de Facebook, que sale de la tuya y no vence. Si anda con esa, no hay que renovar nada.
"""

import getpass
import os
import subprocess
import sys
from datetime import datetime, timezone

import httpx

GRAPH = "https://graph.facebook.com/v27.0"
EJEMPLO = "salacamacua"
CAMPOS_POST = "caption,media_type,media_url,permalink,timestamp"


def pedir(token: str, ruta: str, **params) -> dict:
    """Un GET a la API. Devuelve el JSON, también cuando Meta responde con un error."""
    try:
        respuesta = httpx.get(f"{GRAPH}/{ruta}", params=params, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    except httpx.HTTPError as error:
        return {"error": {"message": f"sin conexión con Meta ({type(error).__name__})"}}
    try:
        return respuesta.json()
    except ValueError:
        return {"error": {"message": f"respuesta rara de Meta (código {respuesta.status_code})"}}


def error(datos: dict) -> str | None:
    if "error" not in datos:
        return None
    e = datos["error"]
    return f"{e.get('message', 'error')} (código {e.get('code', '?')})"


def vencimiento(token: str, acceso: str | None = None) -> str:
    """Cuándo vence una clave y qué permisos tiene (se consulta con la clave del usuario)."""
    datos = pedir(acceso or token, "debug_token", input_token=token).get("data") or {}
    vence = datos.get("expires_at")
    permisos = ", ".join(datos.get("scopes") or []) or "?"
    if vence is None:
        return f"permisos: {permisos}"
    if vence == 0:
        return f"no vence · permisos: {permisos}"
    fecha = datetime.fromtimestamp(vence, timezone.utc).astimezone().strftime("%d/%m/%Y")
    return f"vence el {fecha} · permisos: {permisos}"


def probar(token: str, ig_id: str, cuenta: str) -> bool:
    campos = (f"business_discovery.username({cuenta})"
              f"{{username,name,followers_count,media_count,media.limit(5){{{CAMPOS_POST}}}}}")
    datos = pedir(token, ig_id, fields=campos)
    if problema := error(datos):
        print(f"   ✗ No anduvo: {problema}")
        return False
    perfil = datos.get("business_discovery") or {}
    posts = (perfil.get("media") or {}).get("data") or []
    print(f"   ✓ Anduvo: @{perfil.get('username')} ({perfil.get('name')}), "
          f"{perfil.get('followers_count')} seguidores, {perfil.get('media_count')} posts.")
    for post in posts:
        texto = " ".join((post.get("caption") or "(sin texto)").split())
        imagen = "con imagen" if post.get("media_url") else "sin imagen"
        print(f"     · {post.get('timestamp', '')[:10]}  {post.get('media_type')}, {imagen}: {texto[:90]}")
    return True


def main() -> None:
    cuenta = sys.argv[1].lstrip("@") if len(sys.argv) > 1 else EJEMPLO
    token = os.environ.get("IG_TOKEN") or getpass.getpass("Pegá la clave de acceso (no se va a ver) y apretá Enter: ").strip()
    if not token:
        sys.exit("No pegaste ninguna clave.")

    print("\n1. Tu clave")
    yo = pedir(token, "me", fields="name")
    if problema := error(yo):
        sys.exit(f"   ✗ Meta no la acepta: {problema}\n   Generá una nueva (paso 4 de la guía).")
    print(f"   ✓ Es de {yo.get('name')} · {vencimiento(token)}")

    print("\n2. Tu página de Facebook y la cuenta de Instagram conectada")
    campos_pagina = "name,access_token,instagram_business_account{id,username}"
    paginas = pedir(token, "me/accounts", fields=campos_pagina)
    if problema := error(paginas):
        sys.exit(f"   ✗ No se pudieron ver tus páginas: {problema}\n   ¿Marcaste el permiso pages_show_list?")
    lista = paginas.get("data") or []
    if not lista:
        # Con las páginas nuevas (o dentro de un portfolio), "me/accounts" puede venir vacío aunque la clave tenga
        # permiso sobre la página: se busca la página por su número, que figura en los permisos de la clave.
        datos = pedir(token, "debug_token", input_token=token).get("data") or {}
        ids = {a["scope"]: a.get("target_ids") or [] for a in datos.get("granular_scopes") or []}
        for pid in ids.get("pages_show_list", []):
            pagina = pedir(token, pid, fields=campos_pagina)
            if not error(pagina):
                lista.append(pagina)
        if not lista and ids.get("instagram_basic"):
            print("   · No se pudo leer la página, pero la clave tiene permiso sobre la cuenta de Instagram "
                  f"{ids['instagram_basic'][0]}: se prueba directo con esa.")
            lista = [{"name": "(sin leer)", "instagram_business_account": {"id": ids["instagram_basic"][0], "username": "?"}}]
    if not lista:
        sys.exit("   ✗ Meta no devolvió ninguna página. O no elegiste la página en la ventana de Facebook al generar la clave,\n"
                 "     o la página está dentro de un portfolio comercial (Meta Business Suite) y falta el permiso\n"
                 "     business_management. Ver «Si no aparece ninguna página» en la guía.")
    conectadas = [p for p in lista if p.get("instagram_business_account")]
    for pagina in lista:
        ig = pagina.get("instagram_business_account")
        print(f"   · {pagina.get('name')}: " + (f"conectada a @{ig.get('username')}" if ig else "sin Instagram conectado"))
    if not conectadas:
        sys.exit("   ✗ Ninguna página tiene un Instagram conectado (paso 1 de la guía), o no la elegiste al generar la clave.")
    pagina = conectadas[0]
    ig_id = pagina["instagram_business_account"]["id"]

    print(f"\n3. Leer @{cuenta} con tu clave")
    con_la_tuya = probar(token, ig_id, cuenta)

    print(f"\n4. Leer @{cuenta} con la clave de la página «{pagina.get('name')}»")
    clave_pagina = pagina.get("access_token")
    con_la_de_pagina = bool(clave_pagina) and probar(clave_pagina, ig_id, cuenta)
    if clave_pagina:
        print(f"   (la clave de la página: {vencimiento(clave_pagina, token)})")

    print("\nResultado:")
    if con_la_de_pagina:
        print("   ✓ Anda con la clave de la página: esa es la que conviene guardar, porque no hay que renovarla.")
        if input("   ¿La copio al portapapeles para guardarla en GitHub? (s/n) ").strip().lower().startswith("s"):
            subprocess.run(["pbcopy"], input=clave_pagina.encode(), check=False)
            print("   Copiada. Pegala en GitHub como secreto INSTAGRAM_TOKEN (paso 6 de la guía) y después copiá otra cosa,")
            print("   así no queda en el portapapeles.")
    elif con_la_tuya:
        print("   ✓ Anda con tu clave, pero no con la de la página: hay que renovarla cada 60 días (paso 6 de la guía).")
    else:
        print("   ✗ No anduvo con ninguna. Copiá el mensaje de error de arriba (sin la clave) y lo vemos.")


if __name__ == "__main__":
    main()
