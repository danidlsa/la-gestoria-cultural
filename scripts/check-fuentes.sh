#!/usr/bin/env bash
# Prueba de conectividad: verifica que cada fuente responda y traiga el dato esperado.
# Corre igual en una Mac o en GitHub Actions, para comparar desde dónde se puede scrapear.
# Uso: scripts/check-fuentes.sh
set -u

UA_PROPIO="CarteleraMVD/0.1 (+https://github.com/danidlsa/cartelera-cultural)"
UA_NAVEGADOR="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"

# fase|id|url|marcador que tiene que aparecer en la respuesta
FUENTES='
1|tickantel|https://tickantel.com.uy/shows-sitemap.xml|<loc>
1|redtickets|https://www.redtickets.uy/|"EventName"
1|ticketmaster_uy|https://www.ticketmaster.uy/|event/
1|portal_im|https://eventos.montevideo.gub.uy/jsonapi/node/evento?filter%5Bstatus%5D=1&page%5Blimit%5D=1|node--evento
1|cartelera_mvd|https://cartelera.montevideo.com.uy/|apeliculafunciones
1|sodre|https://sodre.gub.uy/espectaculos/wp-json/wp/v2/espectaculo?per_page=1|"espectaculo"
1|zitarrosa|https://salazitarrosa.montevideo.gub.uy/wp-json/wp/v2/evento?per_page=1|"evento"
1|solis|https://www.teatrosolis.org.uy/home|PROGRAMACI
1|teatro_de_verano|https://teatrodeverano.montevideo.gub.uy/home|Verano
1|galpon|https://www.teatroelgalpon.org.uy/|Galp
1|cinemateca|https://cinemateca.org.uy/calendario|Calendario
2|gaucho|https://www.gaucho.com.uy/shows.php|GAUCHO
2|am|https://am.com.uy/|_next
2|piano_piano|https://pianopiano.uy/agenda/|redtickets
2|ladiaria|https://beneficios.ladiaria.com.uy/category/espectaculos/feed/|<item>
2|sala_del_museo|https://www.saladelmuseo.com.uy/shows.html|/shows/item/
2|peatonal_tours|https://www.peatonaltours.uy/|UYU
'

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

probar() { # url ua marcador -> "codigo bytes encontrado"
  local out="$TMP/resp"
  local meta
  meta=$(curl -sL --compressed -m 25 -A "$2" -o "$out" -w '%{http_code} %{size_download}' "$1" 2>/dev/null || echo "000 0")
  local n=0
  [ -s "$out" ] && n=$(grep -cF -- "$3" "$out" || true)
  rm -f "$out"
  echo "$meta $n"
}

PAIS=$(curl -s -m 10 https://ipinfo.io/country || echo "?")
ORIGEN="máquina local"
[ -n "${GITHUB_ACTIONS:-}" ] && ORIGEN="GitHub Actions"
{
  echo "## Conectividad de fuentes"
  echo
  echo "Desde: **${ORIGEN}** · país de la IP: **${PAIS}** · $(date -u '+%Y-%m-%d %H:%M UTC')"
  echo
  echo "| Fase | Fuente | UA propio | UA navegador |"
  echo "|------|--------|-----------|--------------|"
} > "$TMP/tabla.md"

fallas=0
ok_ids=""
mal=""
while IFS='|' read -r fase id url marcador; do
  [ -z "$fase" ] && continue
  celdas=""
  for ua in "$UA_PROPIO" "$UA_NAVEGADOR"; do
    read -r code bytes n <<< "$(probar "$url" "$ua" "$marcador")"
    if [ "$ua" = "$UA_PROPIO" ]; then etiqueta="propio"; else etiqueta="navegador"; fi
    if [ "$code" = "200" ] && [ "$n" -gt 0 ]; then
      celdas="$celdas | ✅ 200"
    else
      celdas="$celdas | ❌ $code (${bytes} B, marcador: $n)"
      fallas=$((fallas + 1))
      mal="$mal $id[$etiqueta:$code]"
    fi
  done
  case "$celdas" in *❌*) ;; *) ok_ids="$ok_ids $id" ;; esac
  echo "| $fase | $id$celdas |" >> "$TMP/tabla.md"
done <<< "$FUENTES"

cat "$TMP/tabla.md"
[ -n "${GITHUB_STEP_SUMMARY:-}" ] && cat "$TMP/tabla.md" >> "$GITHUB_STEP_SUMMARY"
echo
echo "Pruebas fallidas: $fallas"

# Las anotaciones se ven en la página de la corrida sin iniciar sesión (el resumen y los logs no).
if [ -n "${GITHUB_ACTIONS:-}" ]; then
  echo "::notice title=Conectividad (IP ${PAIS})::OK:${ok_ids:- ninguna} | Fallan:${mal:- ninguna}"
fi
