# Diseño: modelo de datos, pipeline y stack

Propuesta para el MVP de la cartelera. Se apoya en la investigación de fuentes y en datos reales de Tickantel, RedTickets y el portal IM revisados el 30/10/2026.

**Estado: aprobado el 31/10/2026.** El lenguaje es **Python** en todo lo que se pueda, y los flyers se muestran.

---

## Principios

Vienen de las decisiones tomadas al investigar las fuentes:

- **Todo por scraping**, sin carga manual de eventos.
- **Público local**, **solo Montevideo** (Buenos Aires quedó descartado por ahora) y **sin costo**: planes gratuitos, sin APIs pagas.
- **Una fuente rota no rompe la cartelera**: cada fuente conserva su último resultado bueno.
- **Siempre se enlaza a la fuente** para comprar o ver más. No se republican textos largos.

---

## Lo que muestran los datos reales

Esto cambia algunas cosas respecto a lo que se veía en las portadas:

| Fuente | Qué trae el detalle de cada evento | Consecuencia |
|--------|------------------------------------|--------------|
| **Tickantel** | Un `Event` en JSON-LD **por función**, con `startDate` y zona horaria, precio, coordenadas e imagen. El payload trae además cada función con `availabilityStatus` (disponible o agotado) y un texto de horario ("Viernes y Sábado a las 17:30h"). | No hace falta interpretar fechas en texto. |
| **RedTickets** | Bloque `Dates` → `Times` → `Tickets`, con fecha ISO, hora, `soldOut`, precio con y sin cargo, `GeoPoint`, dirección y **productor**. | Lo mismo. La fecha en texto ("Viernes 30 de Octubre") solo aparece en la portada; el detalle la trae estructurada. |
| **Portal IM** | Hay **eventos "paraguas"** (por ejemplo "Música en el Parque", de octubre a noviembre) y **actividades** que dependen de ellos. Las funciones vienen en un párrafo `funciones`, con fecha, fin, zona horaria y, a veces, una regla de recurrencia (`rrule`). | El modelo necesita la idea de **ciclo**. Lo recurrente (con `rrule` o sin fecha) se descarta, según lo decidido. |

Todas las fuentes del MVP traen **coordenadas** o una dirección. Eso permite reconocer la sala por ubicación y no solo por nombre.

---

## Modelo de datos

Cuatro entidades. Los nombres de campo van en español, como el dominio.

### `Lugar`

Catálogo de salas y espacios: `data/lugares.json`.

```json
{
  "id": "teatro-el-galpon",
  "nombre": "Teatro El Galpón",
  "alias": ["Teatro Galpón", "El Galpón", "Galpón Sala Cero"],
  "direccion": "Av. 18 de Julio 1618",
  "barrio": "Cordón",
  "lat": -34.90403,
  "lon": -56.181082,
  "ciudad": "Montevideo",
  "web": "https://www.teatroelgalpon.org.uy"
}
```

- **Se genera automáticamente** a partir de lo que traen las fuentes: los `node--lugar` del portal IM (con coordenadas) y las direcciones de RedTickets y Tickantel.
- **La lista de alias es la única parte mantenida a mano.** Es configuración, no carga de eventos: un archivo chico donde se anota que "Auditorio Adela Reta" y "Auditorio Nacional del Sodre" son el mismo lugar.
- Las **salas internas** ("Sala Cero", "Sala Zavala Muniz") se guardan como `sala` dentro de la función, no como lugares distintos.

### `Evento`

Lo que se muestra en la cartelera: `data/eventos.json`.

```json
{
  "id": "ev_7f3a9c",
  "titulo": "La rebelión de la carne",
  "categoria": "teatro",
  "descripcion_corta": "Unipersonal interdisciplinario entre la danza, el teatro y la performance autobiográfica.",
  "lugar_id": "teatro-el-galpon",
  "ciclo_id": null,
  "funciones": [
    { "inicio": "2026-11-14T20:30:00-03:00", "sala": "Sala Cero", "agotada": false },
    { "inicio": "2026-11-15T20:30:00-03:00", "sala": "Sala Cero", "agotada": false }
  ],
  "precio": { "desde": 650, "hasta": 650, "moneda": "UYU", "gratis": false },
  "entradas": [
    { "url": "https://redtickets.uy/evento/LA-REBELION-DE-LA-CARNE-Sala-Cero/34406/", "via": "redtickets" }
  ],
  "beneficios": [
    { "programa": "la diaria", "tipo": "2x1", "url": "https://beneficios.ladiaria.com.uy/la-rebelion-de-la-carne/" }
  ],
  "imagen_url": "https://files.redtickets.uy/imagenes/....jpg",
  "productor": "Teatro El Galpón",
  "region": "montevideo",
  "fuentes": [
    { "fuente": "redtickets", "id_externo": "34406", "url": "https://redtickets.uy/evento/.../34406/", "visto": "2026-10-31T06:00:00-03:00" },
    { "fuente": "ladiaria", "id_externo": "la-rebelion-de-la-carne", "url": "https://beneficios.ladiaria.com.uy/la-rebelion-de-la-carne/", "visto": "2026-10-31T06:00:00-03:00" }
  ],
  "actualizado": "2026-10-31T06:05:00-03:00"
}
```

- **`subcategoria`** refina la categoría: `comedia_nacional`, `ballet_sodre`, `stand_up`, `cinemateca` y, en música, `clasica`, `tropical` y `rock_pop`.
- **`categoria`** es una lista cerrada: `musica`, `teatro`, `danza`, `humor`, `cine`, `exposicion`, `infantil`, `fiesta`, `festival`, `carnaval`, `tour`, `charla`, `taller`, `otros`. Cada fuente traduce sus categorías a esta lista; si la fuente no informa categoría (Tickantel), se infiere por palabras clave y, como respaldo, por el tipo de sala.
- **`funciones`** es la unidad de tiempo: un evento con 10 funciones es **un** evento, no diez. La cartelera "hoy" muestra los eventos que tienen alguna función hoy.
- **`descripcion_corta`**: como máximo unos 300 caracteres, para no republicar textos ajenos. El resto se lee en la fuente.
- **`imagen_url`**: **el flyer se muestra** (decisión). Se enlaza la imagen original de la fuente, sin copiarla al repo; así el repo no crece y el flyer siempre lleva a la fuente. Si una imagen no carga (porque el sitio bloquea que se muestre desde otra web o porque la borraron), la web muestra un placeholder por categoría.
- **`region`**: hoy siempre `montevideo` (el valor `buenos_aires` quedó en el modelo por si se retoma). Los eventos del interior se descartan al scrapear.

### `Ciclo` (opcional)

Para festivales, temporadas y ciclos: "Música en el Parque", la temporada de la Comedia Nacional, Primavera 0, el Día del Patrimonio. Tiene `id`, `titulo`, `desde`, `hasta` y `url`, y los eventos lo referencian con `ciclo_id`. Sirve para agrupar en la web ("parte de…").

### Datos crudos por fuente

Cada scraper escribe `datos/fuentes/<fuente>.json` con los eventos ya normalizados a este mismo esquema y una cabecera:

```json
{ "fuente": "redtickets", "corrida": "2026-10-31T06:00:00-03:00", "ok": true, "cantidad": 168, "eventos": [ ... ] }
```

**Si una corrida falla** o trae sospechosamente pocos eventos (por ejemplo, menos de la mitad que la anterior), **no se sobrescribe el archivo**: queda el último resultado bueno y se registra el error.

---

## Deduplicación

Un mismo evento puede llegar por varias fuentes. El paso de unificación las cruza en este orden:

1. **Coincidencia exacta por ID externo.** Muchas fuentes enlazan a la ticketera: la diaria, Piano Piano, la Sala del Museo y Gaucho enlazan a RedTickets o Tickantel; el Sodre, el Solís y la Zitarrosa, a Tickantel; El Galpón, a RedTickets. Si dos registros apuntan al mismo evento de una ticketera (o a la misma ficha de Ticketmaster o del Antel Arena), son el mismo, **siempre que además estén en la misma sala o se parezcan en el título**: un enlace puede estar mal (pasó con un beneficio de la diaria de una obra que enlazaba a la entrada de otra, y las dos quedaban fusionadas).
2. **Coincidencia difusa.** Mismo `lugar_id`, alguna función el mismo día (con ±1 hora de tolerancia) y títulos parecidos. La similitud se calcula sin tildes, en minúsculas y sin ruido del tipo "presenta:" o "- Sala Cero".
3. **Fusión.** Se unen las funciones (si una fuente da un día "sin hora" y otra lo da con horario, queda el horario), se juntan `entradas` (un enlace por destino), `beneficios` y `fuentes`, y cada campo se toma de la fuente de mayor prioridad:
   - **sala oficial > ticketera > cartelera agregada > productora > beneficios**.

     Por ejemplo, el título y la descripción salen del sitio de la sala si existe, y el precio y si está agotado, de la ticketera.

**Salas con nombres distintos.** "El Galpón - Sala Cero" se separa en sala ("El Galpón") y sala interna ("Sala Cero"). Dos nombres se consideran la misma sala si, sin palabras genéricas ("teatro", "sala", "espacio", "escuela"…), son equivalentes ("Teatro MANDRÁGORA Escuela de Artes" = "Teatro Mandrágora") y no están a más de 1 km. Lo que no se resuelve así va como alias en `config/lugares_alias.toml`.

**Fechas sin año.** Varias fuentes escriben "13 de noviembre". Si esa fecha pasó hace menos de un mes, ya pasó (no se pasa al año siguiente); si pasó hace más, es del año que viene ("10 de abril" leído en octubre). La diaria se lee desde la fecha de publicación de cada beneficio.

**Salas sin ubicación.** Se buscan en OpenStreetMap por dirección o, si no hay, por nombre; un nombre de una sola palabra ("Sitio") no se busca, porque es demasiado ambiguo.

**El `id` del evento** se deriva de la primera coincidencia estable (ticketera e ID externo). Así no cambia de una corrida a otra y los enlaces a la web no se rompen.

---

## Pipeline

```
 GitHub Actions (cron)              Equipo local en Uruguay (días de semana 11 h)
 ─ 15 fuentes ─────────┐            ┌─ portal IM, Zitarrosa, Ticketmaster.uy
                       ▼            ▼
              datos/fuentes/<fuente>.json   (crudo normalizado, último bueno)
                       │
                       ▼  unificar: lugares + dedupe + fusión
              datos/eventos.json · datos/lugares.json · datos/ciclos.json
                       │
                       ▼  build
              sitio estático en GitHub Pages
```

- **Los datos generados van en una rama aparte, `datos`.** Así `main` tiene solo código y su historial no se llena con un commit de datos por día. Además, el historial de `datos` deja ver cómo cambió la cartelera.
- **GitHub Actions** corre tres veces por día (6:17, 12:17 y 18:17 de Uruguay; fuera de la hora en punto, que es cuando GitHub más atrasa las corridas programadas): sus scrapers, la unificación y el build y deploy de la web.
- **El equipo local** corre sus scrapers (los marcados `corre_en = "local"` en `config/fuentes.toml`), hace commit **solo de sus archivos** en `datos/fuentes/` y pushea a la rama `datos`. La corrida de Actions de las 12 los suma a la unificación y al build. Como cada lado escribe archivos distintos, no hay conflictos; igual se hace `git pull --rebase` antes de pushear.

### Estructura del repo

Ver el [README](../README.md#cómo-está-armado). En resumen: todo el código vive en el paquete `cartelera/` (con `scrapers/`, `unificar.py` y `sitio/`), la configuración en `config/` y los tests en `tests/`, con páginas de ejemplo en `tests/fixtures/`.

**Tests con HTML guardado:** cada scraper tiene un ejemplo real de la página en `tests/fixtures/`, recortado a los bloques de datos que usa (no la página entera, para no publicar contenido ajeno). Si un sitio cambia y el parser se rompe, el test nuevo falla con el HTML nuevo y se arregla rápido. Es la mejor defensa contra el mantenimiento.

---

## Almacenamiento y retención

**No hay base de datos con servidor. La "base" son archivos JSON en la rama `datos` del repo.**

- **Por qué alcanza**: la cartelera activa son del orden de **1.000 a 2.000 eventos**, o sea unos pocos MB de JSON. La web los lee directamente y filtra en el navegador. No hay usuarios, ni escrituras desde la web, ni consultas complejas: no hace falta un motor de base de datos.
- **Qué hay en `datos`**:
  - `fuentes/<fuente>.json`: el último resultado bueno de cada scraper.
  - `eventos.json`, `lugares.json` y `ciclos.json`: la cartelera unificada.
- **Limpieza automática**: en cada unificación, **se descartan las funciones que ya pasaron** (con un margen de un día) y **los eventos que se quedan sin funciones futuras**. Los archivos siempre tienen solo lo vigente, así que no crecen con el tiempo.
- **El historial es gratis**: cada corrida es un commit en `datos`, así que lo que sale de los archivos sigue en el historial de git. Se puede consultar cualquier día pasado sin guardar un archivo histórico aparte.
- **El tamaño del repo**: git guarda solo las diferencias, comprimidas, entre un commit y el siguiente. Con dos corridas por día, la rama `datos` crecería **del orden de decenas de MB por año**, muy lejos del límite recomendado por GitHub (1 GB). Si algún día pesa demasiado, se puede **reiniciar el historial de `datos`** (los datos se regeneran solos), sin tocar `main`.
- **Cuándo cambiaría esto**: si en el futuro hubiera funciones con usuarios (favoritos, avisos por mail) o estadísticas históricas pesadas, se puede sumar **SQLite** como archivo o la capa gratuita de **Supabase**. Para el MVP no hace falta.
  - Ojo con la capa gratuita de Supabase: **pausa los proyectos sin actividad** después de un tiempo.

---

## Seguridad de la corrida local

**El riesgo es bajo**, y se puede bajar más con algunas reglas.

### Qué hace el job

Una vez por día, el programador de tareas del equipo ejecuta código **de este repo**, que hace pedidos HTTP **salientes** a unos pocos sitios públicos, guarda JSON y hace `git push`.

- **No abre puertos ni recibe conexiones.**
- **Nadie puede ejecutar algo en el equipo desde GitHub.** Por eso se eligió una tarea programada y no un runner self-hosted.

### Riesgos y cómo se cubren

| Riesgo | Qué podría pasar | Cómo se cubre |
|--------|------------------|---------------|
| **Código malicioso en el repo** | Si alguien lograra meter código en `main`, el equipo lo ejecutaría con los permisos de su usuario. | Solo vos tenés permiso de escritura. **No se mergean pull requests de terceros sin revisarlos.** Se protege `main` con una regla de GitHub para que no se pueda pushear directo. El job corre siempre desde `main`, no desde otras ramas. |
| **Una dependencia comprometida** (un paquete de Python malicioso) | Lo mismo: código ajeno corriendo en el equipo. | **Pocas dependencias** y conocidas (`httpx`, `pydantic`, `rapidfuzz`, `jinja2`, `python-dateutil`). **Versiones fijadas con hash** (`uv.lock`), así que una actualización maliciosa no entra sola. Un entorno virtual aislado. |
| **Contenido hostil en los sitios scrapeados** | Una página armada para atacar al que la lee. | El job **solo lee JSON y HTML como texto**: no ejecuta JavaScript, no usa navegador headless y no hace nada parecido a `eval` o `pickle` con lo que baja. Parsear texto en Python no ejecuta código. Las fuentes locales son APIs JSON o HTML simple. |
| **Credenciales de GitHub demasiado amplias** | Hoy `git push` usa tus credenciales guardadas, que dan acceso a **todos** tus repos. | El job usa una **deploy key** (una llave SSH) **solo para este repo**. Si se filtrara, solo afectaría a `cartelera-cultural`, y la regla sobre `main` impide que se use para cambiar el código. |
| **Que se suba algo de más** | Un log con rutas o datos del equipo terminando en el repo público. | El job hace `git add` **solo** de los archivos de sus fuentes en `datos/fuentes/` y nunca de otra cosa. Los logs quedan en el equipo. |
| **La IP del equipo** | Esos sitios ven pedidos diarios desde esa IP. Si alguno la bloqueara, también afectaría a quien navegue ese sitio desde ahí. | Volumen muy bajo (una vez por día), User-Agent identificable y pausas entre pedidos. Es poco probable. |

### La web y los workflows

- **Lo que viene de las fuentes no puede ejecutar nada en la web.** Los textos se insertan siempre como texto (Jinja2 con autoescape y, en el navegador, nodos de texto: nunca `innerHTML`). Los enlaces tienen que ser `http(s)`: el modelo de datos rechaza un enlace `javascript:` y descarta una imagen con un enlace raro. Los datos embebidos en la página llevan todos los `<` escapados.
- **El texto de "¿Qué es La Gestoría?"** solo admite enlaces web, de mail o internos.
- **Workflows con permisos mínimos**: nada por defecto; el trabajo que actualiza los datos puede escribir en el repo y el que publica, solo en Pages. El código se baja sin dejar la credencial guardada (`persist-credentials: false`).
- **Actions de terceros fijadas a un commit exacto** (con la versión en un comentario): una versión nueva o comprometida no entra sola. Para actualizarlas, se cambia el hash a mano.
- **Nada personal en el repo**: no hay claves ni tokens (las fuentes son públicas y Wikidata, Nominatim y OpenStreetMap no piden key), y la prueba de conectividad informa solo el país de la IP, no la IP.

### Cómo está armado

- [`scripts/local/correr.sh`](../scripts/local/correr.sh) es el job. Trabaja en un **clon propio** del repo (`~/.cartelera-cultural`), separado de la copia de trabajo, así que lo que estés editando no se mezcla con lo que corre. En cada corrida:
  1. Trae `main` y corre ese código, nunca otra rama.
  2. Trae la rama `datos` (en `datos/` adentro del clon), para que cada fuente compare con su último resultado bueno.
  3. Corre `scrapear --donde local`. Si una fuente falla, queda su último resultado bueno.
  4. Hace commit solo de `datos/fuentes/<fuente>.json` de esas fuentes y pushea a `datos` con la deploy key.
- [`scripts/local/cartelera.plist`](../scripts/local/cartelera.plist) es la plantilla de la tarea programada (`launchd`): días de semana a las 11, con prioridad baja. El log queda en `~/Library/Logs/cartelera-cultural.log`.
- [`scripts/local/instalar.sh`](../scripts/local/instalar.sh) se corre una vez, a mano: genera la deploy key (y muestra la parte pública para pegarla en GitHub), clona el repo y registra el job. Al principio del script están los comandos para desinstalarlo.

Para instalarlo hace falta que `main` tenga este código y que exista la rama `datos` (la crea la primera corrida del workflow).

**Probado de punta a punta (30/10/2026)** contra un repo de prueba local con `main` y `datos`, con el entorno vacío con el que corre la tarea programada: trae el código, corre las 3 fuentes, sube solo sus 3 archivos y resuelve bien un push de Actions en el medio.

**Opcional, si querés más aislamiento**: correr la tarea con un **usuario del sistema aparte**, sin acceso a otros documentos. No me parece necesario para empezar.

---

## Stack

### Python para scrapers y datos, sitio estático simple (decisión)

| Parte | Herramienta | Por qué |
|-------|-------------|---------|
| HTTP | `httpx` | Moderno, con reintentos y timeouts. |
| HTML y JSON-LD | `re`, `html` y `json` de la biblioteca estándar (`cartelera/extraer.py`) | Las fuentes traen los datos en bloques JSON o en HTML simple: alcanza con expresiones regulares y una dependencia menos. |
| Fechas que se repiten | `python-dateutil` | Expande las reglas de repetición (RRULE) del portal de eventos IM. |
| Géneros de la música | API de Wikidata | Abierta, gratis y sin API key (ver "Géneros de la música" en la sección de la web). |
| Esquema | `pydantic` | Valida que cada fuente cumpla el modelo de datos. |
| Dependencias | `uv` | Instala y fija versiones exactas, con hashes (ver Seguridad). |
| Deduplicación | `rapidfuzz` | Similitud de títulos. |
| Tests | `pytest` | Contra el HTML guardado. |
| Web | **Jinja2** (genera HTML estático) y un poco de JavaScript para los filtros | Todo el build en Python. Sin servidor, gratis en GitHub Pages. |

**Regla: Python siempre que se pueda.** Es el lenguaje que mejor conocés, y además tiene el mejor ecosistema para scraping y limpieza de datos.

**La web** también se puede armar en Python para no sumar otro lenguaje: un script que genera páginas HTML con plantillas **Jinja2** a partir de `eventos.json`. Solo los filtros del navegador (categoría, fecha) necesitan unas pocas líneas de JavaScript, que es inevitable en una web. Astro queda descartado.

---

## La web: La Gestoría Cultural

**"La Gestoría Cultural" es solo el nombre.** La web no juega con la metáfora: las secciones y los filtros tienen nombres directos (Agenda, Planeá tu mes, Mapa, Gratis, Promos, Festivales, Especiales; Fecha, Tipo de evento, Excluir, Precio, Sala, Buscar).

**Estética divertida, con esta paleta:**

| Color | Hex | Uso |
|-------|-----|-----|
| Azul cobalto | `#3256A8` | Principal: cabezal, selecciones, calendario |
| Mostaza | `#E4A94A` | Acento, no como fondo permanente: sección activa, día elegido, presentación de cada sección |
| Coral | `#F06C4F` | Segundo acento: filtros activos, 2x1, marcadores del mapa |
| Crema | `#F4E9D5` | Fondo |
| Tinta | `#18264A` | Textos, bordes y sombras; es el fondo en modo oscuro |

**Modo claro u oscuro:** arranca siempre en crema (la identidad de la Gestoría) y cada persona puede pasar a oscuro con el botón ☀/☾ del cabezal; la elección queda en el navegador. No depende del sistema operativo.

Bordes gruesos, sombras sólidas desplazadas y un color de acento por tipo de evento. Tipografías **Bricolage Grotesque** (títulos) y **DM Sans** (texto).

**Filtros activos:** aparecen como chips arriba de los resultados ("Teatro ×", "Este finde ×"), cada uno se borra con un toque, y hay un "Borrar todo" ahí y en el encabezado de los filtros.

**Reparto del trabajo:** Python calcula todo lo posible al generar la página (textos, rangos de precio, subrubros, ciclos, conteos). El JavaScript del navegador solo filtra, dibuja el calendario y el mapa.

| Pieza | Cómo funciona |
|-------|---------------|
| **Carriles por día** (Agenda, Gratis, Promos, Festivales) | Para no scrollear cientos de tarjetas, cada día es un **carril horizontal** ("Hoy · viernes 30 de octubre · 41 eventos") que se desliza de costado, con flechas en la compu; en el celular, en cambio, cada día es una lista (ver "El celular"). Al bajar se pasa de día en día, no de evento en evento. Las temporadas y muestras largas (6 o más fechas a lo largo de 2 semanas o más) van una sola vez, al final, en el carril **"Con muchas fechas · en exhibición"** (lo primero que se ve es hoy). Los fines de semana tienen el título resaltado. Los carriles se dibujan de a 6 días a medida que se baja. Los filtros de fecha (Hoy, Este finde, 7 días, un día del calendario chico) recortan los carriles. Una vista calendario grande en la Agenda se probó y se descartó: no resultó útil para explorar. |
| **El celular** | Pensado para ver eventos en la primera pantalla. **Cabezal compacto**: el nombre en una línea con el botón ☀/☾ y el buscador; la bajada y los contadores quedan para la compu. **Pestañas abajo**, en una barra fija a mano del pulgar: Agenda, Planeá, Mapa y **Más** (Gratis, Promos, Festivales, Especiales y "¿Qué es?"), que se marca cuando la sección elegida está adentro. **Tarjetas en lista**: la imagen chica a la izquierda y al lado tipo, título, sala, fecha, precio con una promo y "+ Mi plan"; el título lleva a las entradas. Cada día es una lista vertical con los primeros 5 y "Ver los 91 eventos" para el resto. Unas 3 tarjetas por pantalla, contra una de antes. |
| **Filtros activos siempre visibles** | La barra con el conteo y los filtros activos (chips con ×) queda fija arriba al bajar. En el celular, esa barra lleva el botón "Filtros (n)". |
| **Filtros en el celular** | Panel lateral que entra desde la izquierda, como en los sitios de compras: arriba de los eventos quedan los atajos de fecha (Hoy, Este finde, 7 días, Todo) y en la barra fija el botón "Filtros", con la cantidad de filtros activos. El panel tiene calendario, tipo, excluir, precio y sala, una × para cerrar y abajo "Ver N eventos". Se cierra también tocando afuera o con Esc. Es accesible como diálogo: el foco entra al panel, lo de atrás queda inerte y al cerrar el foco vuelve al botón. |
| **Mapa** | Leaflet (cargado solo al abrir la sección) sobre los tiles de **OpenStreetMap**: gratis, **sin API key**, con atribución y uso moderado. Los colores se llevan a la paleta con un filtro CSS. Un círculo por sala, más grande cuantos más eventos tiene, y con el color de su tipo: **escenarios grandes** (cobalto; una lista fija en `generar.py`, de unas mil personas para arriba), **teatros, salas y centros culturales** (coral), **museos y exposiciones** (mostaza) y **bares, clubes, plazas y otros** (crema). El tipo sale del nombre de la sala o de lo que se hace ahí, con una leyenda debajo del mapa. Al pasar el mouse el círculo crece y muestra el nombre y la cantidad de eventos; "Ver sus eventos" filtra por esa sala. **Zoom**: con los botones, pellizcando (touchpad o celular) o con la rueda del mouse después de tocar el mapa; antes de tocarlo, la rueda baja la página y aparece una pista, para que el mapa no atrape el scroll. (CARTO pide API key desde 2026, por eso no se usa.) |
| **Sala** | Selector con todas las salas y su cantidad de eventos. El nombre de la sala en cada tarjeta también filtra. |
| **Gratis** | Sección propia. Un evento es gratis si la fuente lo marca así o si todas sus entradas valen $0. |
| **Presupuesto** | Según el precio "desde": **Ganga** (menos de $500), **Accesible** ($500 a $999), **Normal** ($1.000 a $1.600) y **Carito** (más de $1.600). Una entrada a $0 entre otras pagas (por ejemplo, para menores) no cuenta. |
| **Tarjetas** | Un solo enlace: la ticketera si hay; si no, la página de la sala u organizador. **Nunca se enlaza a la Cartelera de Montevideo Portal.** Se ven hasta 2 promos (primero las que nombran un programa) y el resto queda plegado en "+N promos". |
| **Promos** | Salen de los tipos de entrada de RedTickets: programas conocidos (la diaria, Socio Espectacular, Club El País, BROU, Itaú, Santander, BBVA, OCA, AEBU…), socios de clubes o salas, **2x1 para todos** y promos grupales (3x2, dúo). Se descartan las tarifas que no son promociones: cortesías, estudiantes, jubilados, menores, SUA. |
| **Subrubros** | Al elegir un rubro aparecen sus subrubros: Teatro → Comedia Nacional; Danza → Ballet Nacional del Sodre; Humor → Stand up; Cine → Cinemateca; Música → géneros (abajo); y "Otros" en cada uno. Se detectan por palabras clave en título, descripción, productor y sala. |
| **Géneros de la música** | Grupos gruesos: **Clásica y lírica**, **Tropical** y **Rock, pop y otros** (el rock, el pop, el punk, el metal, el rap y todo lo que no se pudo clasificar van juntos). Llevan una nota de que son **experimentales**. Internamente se sigue calculando `rock_pop`. Las fuentes casi no informan el género, así que sale de dos lados: (1) **palabras clave** del título y, si no alcanza, de la descripción y el productor ("sinfónica", "cumbia", "punk"; si se nombran dos, gana la primera); (2) para los títulos que son solo un nombre ("ERUCA SATIVA"), **Wikidata**: se busca al artista y se acepta solo una persona o grupo musical con género y nombre igual al buscado, prefiriendo los de Uruguay y Argentina. Caché en `datos/cache/generos_wikidata.json`, hasta 80 nombres nuevos por corrida, y los no encontrados se reintentan al mes. Los homónimos se corrigen en `config/generos.toml`. **Spotify no sirve:** desde febrero de 2026 no informa géneros a las apps nuevas. MusicBrainz casi no tiene artistas locales. **Cobertura (31/10/2026): 110 de 300 eventos de música (37%)**; la escena local chica y lo tropical son lo que más queda afuera. |
| **Festivales** | Pestaña propia. Es una etiqueta que cruza rubros: un evento es festival si la fuente lo marca así, si el título lo dice ("Festival", "… Fest", Cosquín, Primavera 0, "Fiesta de la/del …") o si es de música y el título nombra **3 artistas o más** ("La Bajada 23, Escarlatina y Sinestesia", "PCE - CUCO - AEF"). Para contar artistas no se cuentan fechas, giras, instrumentos ni el nombre de la sala; un guion separa artistas solo si todas las partes son nombres cortos ("Artista - Nombre del show" es un artista), y la "y" solo en una enumeración con comas ("Julia y lxs Efímerxs" es una banda). |
| **Especiales** | Pestaña con las jornadas grandes del año (Día del Patrimonio, Museos en la Noche, La Noche de las Librerías, Montevideo + Museos, Feria del Libro, Desfile Inaugural, Llamadas, Criolla del Prado), definidas en `config/eventos_especiales.toml`. Cada una tiene una regla para su fecha: el primer sábado de octubre, la Semana de Turismo, o solo el mes ("fecha a confirmar"); cuando se anuncia, se carga `desde`/`hasta`. Una tarjeta por jornada con la próxima fecha, cuánto falta y el sitio oficial. Las actividades se buscan en la cartelera por palabras clave en el título o el ciclo, dentro de esas fechas (con fecha estimada, en todo el mes); si aparecen, la tarjeta las lista y la fecha pasa a ser la del programa. Si falta un mes o menos y no hay nada, la corrida de GitHub Actions abre un issue (`python -m cartelera avisos --github`), una sola vez por edición. Los filtros no se aplican en esta pestaña. |
| **Museos** | Otra etiqueta que cruza rubros, en "Tipo de evento" y en "Excluir": todo lo que viene de las fuentes de museos (Cabildo, Subte, MNAV, Torres García, Gurvich, MAPI y el calendario del MEC), sean exposiciones, visitas, talleres o charlas. |
| **Listas plegadas** | Los tipos de evento muestran los 7 primeros (Museos va junto a Exposiciones) y los programas de beneficios, los 6 con más eventos; el resto queda detrás de "Más tipos (7)" / "Más programas (22)". Lo que está elegido se ve siempre, aunque la lista esté plegada. |
| **Excluir** | Debajo de los tipos de evento, "Excluir" despliega la lista de tipos (como en AO3) y se tocan los que no se quieren ver ("Infantil", "Festivales"). Aparecen como chips "Sin infantil ×" y **quedan guardados en el navegador**, como el plan. En su propia pestaña se ven igual (Carnaval muestra el carnaval aunque esté excluido). |
| **Recorridos y tours** | Rubro para los recorridos a pie: visitas guiadas, caminatas, Peatonal Tours, los "Silent Horror Tour", lo que pasa en el Palacio Salvo y los Paseos de la IM. Se detectan por el título ("visita guiada", "visita nocturna", "recorrido a pie", "horror tour"…), sin confundirlos con las giras de música ("Latin America Tour 2026"). |
| **Exposiciones** | Una exposición (`muestra` en el modelo, con `hasta` si se conoce el cierre) se carga como un día "sin hora" por cada día abierto, hasta el cierre o 60 días adelante; las "actuales" sin cierre se dan por abiertas 30 días y cada corrida lo renueva. Así aparece en el día que se elija y en el carril "Con muchas fechas · en exhibición". La tarjeta muestra el período ("Hasta el 28 feb 2027", "Desde el 28 nov · hasta el 4 abr 2027" o "En exhibición") en lugar de la fecha y la cantidad de funciones. |
| **Talleres y cursos** | Rubro propio (`taller`) para talleres, cursos y clases, para que no se mezclen con los espectáculos. Hoy salen del portal de eventos de la IM. |
| **¿Qué es La Gestoría?** | Pestaña aparte, al final de la fila y con borde punteado, que lleva a una página propia (`que-es.html`), también enlazada desde el pie. El texto se escribe en [`docs/que-es-la-gestoria.md`](que-es-la-gestoria.md) y se publica tal cual: el generador pasa a HTML lo poco de Markdown que usa (párrafos, listas, enlaces y negritas). El texto describe las fuentes en general (ticketeras, carteleras, salas, productoras, beneficios), así que no hace falta tocarlo con cada fuente nueva. |
| **Ciclos** | Se detectan por título: "Ciclo …" explícito, o un mismo prefijo antes de ":" repetido en una sala ("Partículas: …" en la Sala Verdi). Cada tarjeta enlaza a su ciclo. Ya no tienen pestaña propia: tocar el ciclo de una tarjeta filtra la agenda por ese ciclo (chip "Ciclo: …"). |

**Lo que llega con las próximas fuentes:**

- **Comedia Nacional**: los textos de Tickantel no la mencionan; sale del sitio del Solís.
- **Cinemateca**: sale de su propia fuente.

### Accesibilidad

El objetivo es **WCAG 2.2 nivel AA**. Se revisa con [axe](https://github.com/dequelabs/axe-core) en claro y oscuro, en compu y celular, y en la página "¿Qué es?": **sin errores** (31/10/2026).

- **Contraste:** el coral de la marca no alcanza como letra ni con letra blanca encima (3:1). Los fondos coral llevan letra tinta (4,9:1) y el texto coral usa un tono propio (`--coral-texto`, más oscuro en claro y más claro en oscuro). Los días del calendario chico no pasan de un 62 % de cobalto, para que el número siempre se lea.
- **Teclado:** el primer Tab muestra "Saltar a los eventos". Todo es un botón o un enlace de verdad, con contorno de foco mostaza (también el buscador).
- **Lectores de pantalla:** los filtros y pestañas dicen si están activos (`aria-pressed`); cada "＋ Mi plan" dice de qué evento y función es; los días del calendario dicen fecha y cantidad de eventos; el conteo de resultados se anuncia al cambiar (`aria-live`); los flyers son decorativos (el título está en el texto).
- **Tamaños:** ningún texto con información por debajo de unos 12 px; los controles tienen al menos 24 × 24 px (los del celular, 40 px).
- **Movimiento:** con "reducir movimiento" activado en el sistema no hay animaciones ni desplazamientos suaves.
- **Mapa:** los puntos no se manejan con teclado; la alternativa es el selector de sala, que filtra lo mismo.

### Planeá tu mes

Sección para armar el plan del mes y llevarlo al calendario.

- **Mes**: por defecto, el siguiente; se cambia con las flechas del calendario del plan. Los demás filtros (tipo, precio, sala, búsqueda) siguen funcionando: sirve para planear, por ejemplo, "un mes de teatro barato".
- **Un calendario que se va llenando**: el mes arranca vacío, con el calendario compacto (casilleros bajos), que crece cuando se suma lo primero. Cada casillero muestra cuántas opciones hay ese día ("42 opciones"); al tocarlo, la página baja a esas opciones. Lo que elegís aparece escrito en su día (hora y título, con el color de su tipo) y se quita con ×. En el celular, cada elección es un punto de color y el detalle está en la lista "Mi plan", que ahí arranca abierta.
- **Lista de opciones por día**, debajo del calendario. Cada día es un desplegable cerrado ("Domingo 1 de noviembre · 56 opciones · 1 en tu plan") y, adentro, cada tipo de evento otro ("Teatro 22", "Cine 12"…), del más numeroso al menos; las funciones van por hora. Tocar "X opciones" en el calendario abre ese día. Lo abierto queda abierto al sumar o quitar algo. con "↑ Ver mi mes" para volver: una fila por evento y día, con un botón por horario. **Se eligen funciones, no eventos:** de una obra con diez fechas, elegís a cuál vas. También se agrega desde cualquier tarjeta de la Agenda ("＋ Mi plan" toma la función que muestra la tarjeta).
- **Mi plan**: lo elegido, ordenado por fecha. Cada función tiene su enlace "Google Calendar" y se puede quitar. El calendario lateral marca con un punto coral los días que tienen algo elegido.
- **Botones con ícono**, sin explicaciones: **Google Calendar** (con una sola función abre el evento en Google; con más, abre la lista del plan, que tiene un enlace a Google por función, porque Google no importa varios eventos por enlace), **Apple / Outlook** (el archivo .ics), **WhatsApp**, **Imprimir** y **Copiar**. Los íconos de marca son de Simple Icons (CC0).
- **Exportar**: "Apple / Outlook" arma en el navegador un archivo estándar (RFC 5545), validado con la librería `icalendar`. Se importa en Google Calendar (Configuración → Importar), Outlook o Apple.
  - Las horas van en UTC, así que se ven bien en cualquier zona horaria.
  - Como las fuentes no informan cuándo termina cada función, la duración se estima en **2 horas** y se aclara en la descripción.
- **Para quien no usa calendarios digitales**:
  - **Imprimir** (o guardar PDF): arma una hoja A4 apaisada por mes, con un calendario en grilla (tipo "para la heladera") con lo elegido escrito en cada día, y abajo el detalle con sala, dirección y precio. Se genera en el navegador y se imprime con el diálogo del sistema, que también permite guardar como PDF.
  - **WhatsApp**: abre WhatsApp con el plan como mensaje (fecha, título, sala, precio y enlace de entradas), listo para mandarse a uno mismo o al grupo.
  - **Copiar**: el mismo mensaje, para pegarlo donde sea (mail, notas, otra app).
  - Idea pendiente: una imagen del plan para compartir en historias.
- **Guardado**: el plan queda en el navegador (`localStorage`), sin cuentas ni servidor. Al volver a abrir la página se descartan las funciones que ya pasaron o que salieron de la cartelera. Si el navegador no permite guardar (modo privado), el plan dura lo que la pestaña.

### Eventos sin coordenadas

El filtro de Montevideo va por coordenadas. Si un evento llega sin coordenadas, entra solo si su sala ya está en el catálogo **con** coordenadas: porque otro evento de esa misma sala (de cualquier fuente) sí las trajo, o porque la sala está en `config/lugares_alias.toml` y se cruzó con una que tenía ubicación. Si no, se descarta: no hay forma segura de saber si es de Montevideo. Las actividades municipales en muchos barrios a la vez van en el lugar "Varios barrios de Montevideo", que en `config/lugares_alias.toml` tiene el punto de la Intendencia y `solo_por_nombre = true`: así no se le suman por cercanía los eventos que sí son en la Intendencia.

---

## Primera iteración del MVP

1. Esqueleto del repo, `scrapers/comun` y el modelo con `pydantic`.
2. **Scrapers de Tickantel y RedTickets**: juntas cubren la mayoría de las salas. Incluyen sus tests con HTML guardado y el filtro de Montevideo.
3. **Unificación mínima**: catálogo de lugares, deduplicación entre esas dos y `eventos.json`.
4. **Workflow de GitHub Actions** con cron, escribiendo en la rama `datos`.
5. **Página mínima** con "hoy", "este fin de semana" y filtro por categoría, para ver los datos de verdad.

Después se suman de a una las demás fuentes del MVP (portal IM con la corrida local, Cartelera de Montevideo Portal, Sodre, Zitarrosa, Solís, Teatro de Verano, Galpón y Cinemateca).

---

## Preguntas abiertas

Ninguna por ahora.
