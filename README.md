# Cartelera cultural de Montevideo

Teatro, música, danza y más, de todas las salas de Montevideo en un solo lugar. Todo sale de scraping automático de fuentes públicas, sin carga manual. El proyecto es sin fines de lucro.

- [docs/fuentes.md](docs/fuentes.md): qué fuentes hay, cómo se scrapea cada una y qué se decidió.
- [docs/diseno.md](docs/diseno.md): modelo de datos, pipeline, almacenamiento y seguridad.
- [docs/que-es-la-gestoria.md](docs/que-es-la-gestoria.md): el texto de la pestaña "¿Qué es La Gestoría?" de la web.

## Cómo correrlo

Hace falta [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                   # instala las dependencias (versiones fijadas en uv.lock)
uv run python -m cartelera scrapear       # corre los scrapers y guarda datos/fuentes/<fuente>.json
uv run python -m cartelera unificar       # arma datos/eventos.json y datos/lugares.json
uv run python -m cartelera sitio          # genera la web en sitio_generado/
uv run pytest                             # tests (usan páginas de ejemplo de tests/fixtures/)
```

Para correr una sola fuente: `uv run python -m cartelera scrapear redtickets`. Algunas fuentes solo responden desde Uruguay, así que no corren en GitHub Actions (`corre_en = "local"` en `config/fuentes.toml`).

## Cómo está armado

```
cartelera/
├── modelo.py        # Evento, Funcion, Lugar… (pydantic)
├── http.py          # cliente HTTP: User-Agent propio, robots.txt, pausas y reintentos
├── extraer.py       # JSON-LD, payload de Next.js, objetos JSON embebidos
├── geo.py           # filtro de Montevideo por coordenadas
├── categorias.py    # clasificación por palabras clave
├── generos.py       # género de la música: palabras clave y, de respaldo, Wikidata
├── scrapers/        # un módulo por fuente
├── unificar.py      # catálogo de lugares, deduplicación, fusión y limpieza de lo vencido
└── sitio/           # plantilla Jinja2, estilos y filtros de la web
config/
├── fuentes.toml         # dónde corre cada fuente (GitHub Actions o local)
└── lugares_alias.toml   # nombres alternativos de las salas (lo único mantenido a mano)
scripts/local/           # la corrida programada de las fuentes que no corren en GitHub Actions
```

Los datos generados viven en la rama `datos`, no en `main`. El workflow [`cartelera.yml`](.github/workflows/cartelera.yml) actualiza todo tres veces por día y publica la web en GitHub Pages.
