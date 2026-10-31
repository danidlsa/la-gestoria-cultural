# Fuentes y técnicas de scraping

Research de fuentes para la cartelera cultural de Montevideo (con walking tours locales). Buenos Aires se investigó y quedó descartado por ahora (ver sección 6).
Fecha: **30 de octubre de 2026**.

Cada sitio se probó con requests reales desde Uruguay (HTML, `robots.txt`, sitemaps, APIs internas y, en algunos casos, el navegador para ver el tráfico de red), no solo con búsquedas.
Lo que dice **"a verificar"** no se pudo confirmar.

**Escalas usadas**

- **Esfuerzo**: S = horas · M = 1-3 días · L = una semana o más, con mantenimiento continuo.
- **Viabilidad**: qué tan estable y completo es el dato. **Alta** = API o JSON estructurado · **Media** = HTML parseable que se puede romper · **Baja** = anti-bot, imágenes o datos dispersos.

---

## Estado de implementación (30/10/2026)

| Fuente | Estado | Qué aporta en la cartelera unificada |
|--------|--------|--------------------------------------|
| Tickantel | ✅ scraper | ~145 espectáculos: Solís, Sodre, Antel Arena, salas de la IM |
| RedTickets | ✅ scraper (catálogo completo, con caché) | ~500 eventos: salas chicas, bares, fiestas; promos de las entradas |
| Sodre | ✅ scraper (endpoint JSON del calendario) | Hora de fin, elencos estables (Ballet Nacional del Sodre), títulos limpios; cruza exacto con Tickantel |
| Cinemateca | ✅ scraper (calendario + JSON-RPC de Odoo) | Cartelera semanal de Cinemateca, con ciclos y duración |
| Cartelera de Montevideo Portal | ✅ scraper | ~115 obras de teatro (más de 50 que no estaban en ninguna ticketera), con promos |
| Teatro Solís | ✅ scraper (MVD CMS) | Sala interna, género y **Comedia Nacional** |
| Teatro de Verano | ✅ scraper (MVD CMS) | Programación del Teatro de Verano |
| El Galpón | ✅ scraper | Sala interna, hora de fin y promos (BROU, la diaria, socios) |
| Portal de eventos IM | ✅ scraper (JSON:API, corre local) | Actividades municipales (Murga Joven, Carnaval de las Promesas, Atlantidoc, obras del programa Fortalecimiento de las Artes) y talleres barriales, casi todo gratis. Hoy son ~24 |
| Sala Zitarrosa | ✅ scraper (HTML, corre local) | ~24 espectáculos, con sala, ciclos (MAREA, Fest Jazz), precios y promos (la diaria, Club El País); cruza exacto con Tickantel |
| Ticketmaster.uy | ✅ scraper (Crowder, corre local) | Conciertos internacionales grandes. Hoy tiene uno solo (Foo Fighters, Estadio Centenario) |
| Sala del Museo | ✅ scraper (HTML de Joomla) | 12 shows con fecha, hora, imagen y enlace a RedTickets: cruza exacto |
| Gaucho | ✅ scraper (JSON público de su web) | Anuncios tempranos de shows grandes (Pixies, Babasónicos, Foo Fighters), con sala y enlace de entradas |
| Piano Piano | ✅ scraper (HTML de la agenda) | ~20 shows, obras y fiestas con tipo, sala y enlace; descarta los del interior y el deporte |
| Beneficios de la diaria | ✅ scraper (RSS) | Marca el 2x1 de la diaria en ~100 eventos: casi todos enlazan a RedTickets o Tickantel y se unen exacto |
| Fever | ✅ scraper (JSON-LD) | Conciertos Candlelight con fecha, lugar y precio. Los tours y talleres sin fecha no entran |
| Museos de la IM (Cabildo y Subte) | ✅ scraper (Drupal) | Exposiciones abiertas: el Cabildo con su período por mes, el Subte con su lista de actuales. Entrada libre |
| MNAV | ✅ scraper (HTML) | Exposiciones actuales y próximas con fecha exacta, y unas 20 actividades por mes (talleres, charlas, cine) |
| Museo Torres García | ✅ scraper (HTML) | Exposiciones actuales (sin fecha de cierre) |
| Museo Gurvich | ✅ scraper (HTML de WordPress) | Exposiciones con período ("Del 05 nov 2026 Al 15 jun 2027") y las actividades de la agenda de la portada |
| MAPI | ✅ scraper (HTML de WordPress) | Exposiciones actuales (sin fecha de cierre) |
| Calendario del MEC | ✅ scraper (HTML de gub.uy) | Visitas, inauguraciones y talleres en museos nacionales de Montevideo; deja afuera lo virtual y lo de otros departamentos |
| Museo Blanes, Museo de las Migraciones | ⏸ no por ahora | Mezclan exposiciones viejas, convocatorias e inauguraciones sin fecha de cierre: no se puede saber qué está abierto |
| AM Producciones | ⏸ no por ahora | Sus shows se cargan en el navegador desde una base de datos (con una clave de cliente de su sitio). Hoy tiene un solo show próximo (Foo Fighters), que ya entra por Ticketmaster y Gaucho |
| Teatro Circular | ⏸ no por ahora | Su web no tiene una cartelera actualizada; sus obras entran por RedTickets |
| Passline | ⏸ no | Detrás de Cloudflare con chequeos anti-bot, y el país se elige con JavaScript. No se saltean esas protecciones |
| Peatonal Tours | ✔️ ya cubierto | Sus recorridos con fecha entran por RedTickets; la web no publica fechas propias |
| Día del Patrimonio, Museos en la Noche | ⏳ anuales | Guías en PDF una vez por año; si la IM los carga en su portal, entran solos |

**Detalles de las fuentes locales:**

- **Portal de eventos IM**: un "evento" del portal es un paraguas (Encuentro de Murga Joven, Envejecimiento activo) y cada "actividad" es lo que pasa en un lugar y una fecha. Se leen las actividades (`/jsonapi/node/actividad`, con sus funciones, lugares, categoría y público incluidos en el mismo pedido) y el paraguas queda como ciclo.
  - **Entra todo menos el deporte** (decisión del 30/10/2026; antes se tomaba solo lo que tenía fecha): también recreación, gastronomía, institucional y **talleres, cursos y clases**, que van en su propia categoría, "Talleres y cursos". Las actividades con funciones repetidas (una obra de jueves y viernes durante seis semanas, un taller semanal hasta diciembre) entran con cada función expandida, hasta seis meses adelante.
  - **Se descartan las que se repiten sin fecha de fin**: en el portal son actividades viejas (de 2025) o de vacaciones que nadie dio de baja, y si no se cortan aparecerían todas las semanas para siempre.
  - **El audiovisual del portal entra como cine** (decisión): son proyecciones gratuitas, como las de Atlantidoc en centros culturales. "Cine solo Cinemateca" se refiere a no sumar las cadenas comerciales.
  - El portal carga una actividad por fecha para algunos ciclos ("Murga Joven: domingo 15 de noviembre"): se unen en un solo evento con varias funciones.
  - **Una actividad en 5 lugares o más** (por ejemplo, "Talleres de música: canto colectivo", en 9 barrios) va en **una sola tarjeta**, con el lugar "Varios barrios de Montevideo". El lugar de cada función queda guardado y la tarjeta lo muestra en un desplegable ("En 9 lugares"). En el mapa, ese lugar va en la explanada de la Intendencia, que organiza estas actividades. Con menos de 5 lugares sigue habiendo una tarjeta por lugar. El mínimo está en `MINIMO_PARA_JUNTAR_LUGARES`, en `cartelera/scrapers/portal_im.py`.
  - Los enlaces de paginación que devuelve la API usan `http://`, y por ahí el servidor corta la conexión: se pasan a `https://`.
  - Algunos lugares tienen la latitud y la longitud invertidas: se ordenan por rango.
  - Los "eventos" paraguas que no tienen actividades (por ejemplo, Música en el Parque) no se toman, porque traen un rango de fechas y no funciones.
- **Sala Zitarrosa**: la página `/programacion/` lista lo próximo y cada ficha trae funciones (día sin año y hora AM/PM), sala, precios, promos y el enlace a Tickantel. La API de WordPress (`/wp-json/wp/v2/evento`) no informa la fecha, así que no se usa.
- **Ticketmaster.uy**: la portada enlaza a cada evento y la ficha trae un JSON (`bootstrapData`) con nombre, categoría, lugar con coordenadas y funciones. Si las funciones no están publicadas (entradas agotadas), la fecha sale de la descripción y queda sin hora. No informa precios en un formato legible.

Las salas que ninguna fuente ubica se geolocalizan por dirección o nombre con Nominatim (OpenStreetMap), con caché en `datos/cache/geocodificacion.json`, y las salas conocidas pueden llevar coordenadas en `config/lugares_alias.toml`.

---

## Decisiones tomadas

- **Todo sale por scraping**, sin carga manual.
- **El público es quien vive en Montevideo**, no el turista extranjero. Se descartan los tours y experiencias pensados para visitantes (Viator, GetYourGuide, Civitatis, excursiones para cruceros, free tours de plataformas internacionales).
- **El proyecto es sin costo y sin fines de lucro**: no hay afiliados, comisiones ni publicidad. **Se deja de lado todo lo que genere costos**: servicios pagos de scraping, APIs de LLM, hosting pago.
- **Alcance geográfico: solo Montevideo.** Tickantel, RedTickets y la categoría Turismo traen eventos del interior: hay que filtrarlos por departamento.
- **Cine: solo la cartelera de Cinemateca.** Quedan fuera las cadenas comerciales (Life, Movie, Grupocine) y no hace falta coordinar con Cine Uruguay.
- **Portal IM: todo menos el deporte** (desde el 30/10/2026; antes era solo lo que tenía fecha). Los talleres, cursos y clases van en su propio rubro.
- **Buenos Aires: descartado por ahora** (decisión del 31/10/2026). La investigación queda en la sección 6 por si se retoma.
- **MVP con Solís, Teatro de Verano y El Galpón**, además de las ticketeras. Parte de su programación ya llega por Tickantel o RedTickets, pero sus sitios suman lo que no pasa por ahí (funciones gratuitas, venta en boletería o en la web propia del Galpón).
- **Productoras**: Gaucho, AM y Piano Piano; se suman más de a poco.

---

## Resumen

| # | Grupo | Valor para la cartelera | Esfuerzo | Viabilidad | Prioridad |
|---|-------|-------------------------|----------|------------|-----------|
| 4 | Ticketeras (Tickantel, RedTickets, Ticketmaster.uy) | Muy alto: cubren la mayoría de las salas, grandes y chicas | S-M | **Alta** | **1** |
| 2 | Carteleras existentes (portal de eventos IM, Cartelera de Montevideo Portal) | Alto: teatro y eventos municipales ya agregados | S | **Alta** | **1** |
| 1 | Webs de salas grandes | Medio: detalle y lo que no pasa por ticketeras | S-M (sitio por sitio) | Media-Alta | **1** (Sodre, Zitarrosa, Solís, Teatro de Verano, Galpón, Cinemateca) · 2 (resto) |
| 5 | Productoras (Gaucho, AM, Piano Piano) | Medio: anuncios antes de que salgan las entradas | S | Alta | 2 |
| 3 | Redes sociales (Instagram) | Alto para lo under, pero sin costo solo es viable a medias | L | Baja | En pausa |
| 7 | Walking tours y experiencias | Medio-alto: suma una categoría que casi ninguna cartelera tiene | S-M | Alta | 2 |
| 6 | Buenos Aires y festivales | Alto para vos, bajo volumen | M | Media | Descartado por ahora |

### Hallazgos clave

1. **Tickantel, RedTickets y Ticketmaster.uy cubren gran parte de la cartelera**, y las tres traen los datos estructurados en el HTML, sin necesidad de navegador headless.
   - Tickantel vende el Solís, el Antel Arena y salas del Sodre.
   - RedTickets cubre las salas chicas (Montevideo Music Box, Castillo Pittamiglio, Ducón, Camacuá…).
   - Ticketmaster.uy tiene los conciertos internacionales grandes (por ejemplo Foo Fighters 2027).
2. **El portal de eventos de la Intendencia tiene una API JSON abierta** (Drupal JSON:API) con eventos, actividades y lugares georreferenciados, más costo, categoría y fechas. Es la mejor fuente para lo gratuito y municipal.
3. **Ya existe [cineuruguay.com](https://cineuruguay.com), que resuelve el cine comercial.** Junta 39 salas desde 19 fuentes en un JSON abierto. **No lo usamos** (solo nos interesa Cinemateca), pero confirma qué técnicas funcionan: APIs de las cadenas, el WordPress de la Zitarrosa e Instagram con OCR.
4. **Varias salas exponen APIs de WordPress**: el Sodre (`espectaculo`) y la Zitarrosa (`evento`, `festival`, `artista`). Son de las fuentes más estables.
5. **Hay plataformas compartidas, y con un parser se cubren varios sitios**:
   - *MVD CMS* de la IM: Teatro Solís y Teatro de Verano.
   - *Crowder*, la plataforma de Ticketmaster en Latinoamérica: Ticketmaster.uy y All Access (Buenos Aires).
   - *WordPress*: Sodre, Zitarrosa, El Galpón, Teatro Circular y Cosquín Rock.
6. **RedTickets no es RED UTS.** Ticketmaster compró RED UTS (agosto de 2026), que hoy tiene muy pocos eventos y va a migrar a ticketmaster.uy. RedTickets es otra empresa y no se ve afectada.
7. **"Primavera 0" es uruguayo**: es el festival de **Gaucho** (trajo a The Cure, Blur y Nick Cave). Por eso va en el grupo 5, no en Buenos Aires. El de Buenos Aires es **Primavera Sound BA** (28 y 29 de noviembre de 2026, Costanera Sur).
8. **Bloqueos de IP**: desde una IP de fuera de Uruguay, Ticketmaster.uy, All Access y los sitios de la IM no respondían o daban 403; desde Uruguay andan todos. **Los scrapers tienen que correr desde una IP que estos sitios acepten** (ver Infraestructura).
9. **[Vamos Eventos](https://www.vamoseventos.com) es competencia, no fuente.** Es un agregador cerrado con más de 100 ciudades. Sus términos **prohíben el scraping** y bloquea los bots con un checkpoint de Vercel (ver sección 2).
10. **El dominio del Castillo Pittamiglio (`castillopittamiglio.org`) fue tomado por un sitio de apuestas.** No hay que usarlo ni enlazarlo. Las entradas y visitas del Castillo están en RedTickets.
11. **Los walking tours locales salen casi gratis**: la categoría Turismo de RedTickets (Peatonal Tours, visitas al Palacio Salvo, Castillo Pittamiglio) y la categoría Paseos del portal IM se cubren con scrapers que ya están en la fase 1. Hay que modelar los tours **recurrentes** aparte de los eventos con fecha (ver sección 7).
12. **Lo que sigue bloqueado aunque se pruebe desde Uruguay** (anti-bot real, no hay que intentar saltearlo): Songkick, Bandsintown, Resident Advisor y Abitab (que muestra un desafío de Cloudflare).

---

## 1) Salas grandes de Montevideo

> **Para validar**: marcá qué salas querés y si falta alguna. Las que dicen "sin sitio verificado" las conozco como salas relevantes, pero no encontré o no probé su web.

| Sala | Sitio | Tecnología detectada | Técnica | Esfuerzo | Viabilidad | Notas |
|------|-------|----------------------|---------|----------|------------|-------|
| Teatro Solís (y Sala Zavala Muniz, Delmira Agustini) | [teatrosolis.org.uy](https://www.teatrosolis.org.uy/home) | *MVD CMS* de la IM (ASP.NET), HTML del servidor | Parseo HTML de las secciones de programación | M | Media | **Vende por Tickantel**, así que lo básico ya llega por ahí. El sitio suma el detalle de los ciclos (Comedia Nacional, Filarmónica, Lírica). **Mismo CMS que el Teatro de Verano**: un parser sirve para los dos. |
| Auditorio Nacional del Sodre (Adela Reta, Hugo Balzo, Nelly Goitiño) | [sodre.gub.uy/espectaculos](https://sodre.gub.uy/espectaculos/) | WordPress | **API REST** `/wp-json/wp/v2/espectaculo`, con taxonomías `lugar`, `sala-espacio` y `etiqueta-espectaculo`. Las fechas de función salen del HTML del detalle. | S | **Alta** | El campo `modified` permite traer solo lo que cambió. Tiene sitemap. `auditorio.uy` tiene el certificado vencido o mal configurado: usar `sodre.gub.uy`. |
| Sala Zitarrosa | [salazitarrosa.montevideo.gub.uy](https://salazitarrosa.montevideo.gub.uy) | WordPress (IM) | **API REST** `/wp-json/wp/v2/evento` (981 eventos históricos, paginable), más los tipos `festival` y `artista`. La fecha de función sale del detalle (`/espectaculo/<slug>/`). | S | **Alta** | El campo `modified` sirve para traer solo lo nuevo. |
| Teatro de Verano | [teatrodeverano.montevideo.gub.uy](https://teatrodeverano.montevideo.gub.uy/home) | *MVD CMS* (igual que el Solís) | Reusar el parser del Solís | S (si ya está el del Solís) | Media | Clave en verano y en Carnaval. Las entradas de Carnaval se venden por Abitab, que está bloqueado: el dato tiene que salir de acá o del portal de la IM. |
| Sala Verdi | [salaverdi.montevideo.gub.uy](https://salaverdi.montevideo.gub.uy) | Drupal 7 (sitio viejo de la IM) | Parseo HTML o **vía portal de eventos IM / Tickantel** | S-M | Media | No tiene una sección de cartelera clara: es mejor tomarla de otra fuente. |
| Teatro El Galpón | [teatroelgalpon.org.uy](https://www.teatroelgalpon.org.uy) | WordPress, sin tipo de contenido de eventos | Parseo HTML de la cartelera | M | Media | Su `robots.txt` **bloquea explícitamente a los bots de IA** (GPTBot, anthropic-ai, CCBot). Un scraper propio no entra en esa lista, pero conviene ir con cuidado: User-Agent claro y poca frecuencia. |
| Teatro Circular | [teatrocircular.org.uy](https://www.teatrocircular.org.uy) | WordPress | API REST o HTML | S-M | Media | Sufrió una inundación en septiembre de 2025 y estaba por reabrir. |
| Antel Arena | [antelarena.com.uy](https://www.antelarena.com.uy) | CMS Carbonhouse, sección `/events` | Parseo HTML | S | Media | **Todas las entradas enlazan a Tickantel**: con Tickantel ya alcanza y esto sirve de respaldo. |
| Montevideo Music Box | Sin sitio propio detectado | — | **Vía RedTickets** | — | Alta | Aparece en RedTickets con dirección completa. |
| Cinemateca | [cinemateca.org.uy/calendario](https://cinemateca.org.uy/calendario) | Odoo | Parseo HTML del calendario | S | Media | **Única fuente de cine** (decisión). Odoo arma el calendario en el servidor, así que se parsea sin headless. |
| Centro Cultural de España | [ccemontevideo.aecid.es](https://ccemontevideo.aecid.es/) | Liferay | Parseo HTML por categoría | M | Media | Muestras, cine y charlas. |
| MNAV | [mnav.gub.uy](https://mnav.gub.uy/cms.php?id=actividades) | CMS propio en PHP | Parseo HTML | S | Media | Exposiciones de larga duración. |
| Estadio Centenario, Parque Rodó, Velódromo | Sin sitio de cartelera | — | Vía productoras, Ticketmaster.uy y Tickantel | — | — | Acá se hacen los conciertos más grandes. |
| **Sala del Museo** (Museo del Carnaval) | [saladelmuseo.com.uy](https://www.saladelmuseo.com.uy/) | Joomla con el componente ZOO, HTML del servidor | Parseo HTML de `/shows.html` (12 shows hoy) y de cada `/shows/item/<slug>.html`, que trae la fecha ("Domingo 22 Nov") y el enlace a RedTickets | S | Media-Alta | Sala importante de música (Coti, Cuatro Pesos de Propina, Eruca Sativa). Las entradas también llegan por RedTickets: el sitio sirve para confirmar y como respaldo. |
| Live Era | Sin sitio propio | — | **Vía RedTickets** | — | Alta | Muchos shows internacionales de rock y metal (Saratoga, Dying Fetus, Ayax & Prok). |
| Teatro Victoria | Sin sitio propio | — | **Vía Cartelera de Montevideo Portal** y ticketeras | — | Alta | |
| Teatro Stella d'Italia | Tiene web, pero la agenda no funciona | — | **Vía Cartelera de Montevideo Portal** y ticketeras | — | Media | |
| Castillo Pittamiglio | ⚠️ `castillopittamiglio.org` **fue tomado por un sitio de apuestas** | — | **Vía RedTickets** (categoría Turismo: "Entrada General Castillo Pittamiglio") | — | Alta | No usar ni enlazar el dominio. |
| Teatro del Notariado, Sala Camacuá, Ducón | Sin sitio verificado | — | Vía RedTickets o Tickantel | — | — | Aparecen como lugar en RedTickets y en Vamos. |

**Cines comerciales: fuera de alcance** (decisión). Quedan anotados por si cambia el criterio. Estos endpoints salen de la lista de fuentes que publica Cine Uruguay; no los probé directamente:

| Cadena | Endpoint |
|--------|----------|
| Life Cinemas | `lifecinemas.com.uy/api/movie`, `/api/complex/active` |
| Movie | `api.movie.com.uy/api/shows/cinema/weekly` |
| Grupocine | `grupocine.com.uy/api/peliculas`, `/api/complejos` |
| Cine Universitario | `cineuniversitariodeluruguay.org.uy/wp-json/tribe/events/v1/events` |
| Cine Opera | Prestashop (`cinesopera.com`) |

---

## 2) Carteleras existentes

| Fuente | Qué cubre | Tecnología | Técnica | Esfuerzo | Viabilidad | Notas |
|--------|-----------|------------|---------|----------|------------|-------|
| **[Portal de eventos de la IM](https://eventos.montevideo.gub.uy)** | Eventos y actividades municipales, centros culturales, gratuitas, Carnaval | Drupal | **JSON:API abierta** en `/jsonapi`, con recursos `node--evento`, `node--actividad` y `node--lugar` (con lat/lon). Trae `field_costo`, `field_fechas`, `field_fechas_horarios`, `field_categoria` y la fecha de baja. Se ordena por `changed.value` y se pagina. Categorías: artes escénicas, artes visuales, audiovisual, carnaval, música, literatura, etc. | S | **Alta** | **La mejor fuente para lo gratuito y lo barrial.** Usar `include=` para traer fechas y categorías en la misma llamada. **Solo eventos con fecha** (decisión): usar `node--evento` y descartar talleres, actividades permanentes y deporte. |
| [Cartelera de Montevideo Portal](https://cartelera.montevideo.com.uy) (ex cartelera.com.uy) | Cine, **teatro**, recitales, infantil, estrenos | ASP.NET, HTML del servidor | Parseo HTML de las secciones `apeliculafunciones.aspx?…OBRA…` (teatro) y `…FILM…` (cine), más la vista por fechas | M | **Alta** | **La mejor fuente agregada de teatro.** El `robots.txt` permite el acceso (`use=reference`, `ai-train=no`). Activa: la portada estaba fechada hoy. |
| [Cine Uruguay](https://cineuruguay.com) | Cine: 39 salas, cineclubes y festivales | Sitio estático con JSON | `GET /data/programacion.json` (1,1 MB) | — | — | **Fuera de alcance** (solo Cinemateca). Sirve como referencia: cada función trae `fuente` y `confianza`, un buen modelo para copiar. |
| [Descubrí Montevideo](https://www.descubrimontevideo.uy/que-hacer) | Agenda semanal turística | Drupal, HTML del servidor | Parseo HTML de la agenda semanal | S-M | Media | Selección curada, no exhaustiva. |
| [Fever](https://feverup.com/es/montevideo-uruguay) | Experiencias (Candlelight, muestras inmersivas) | HTML del servidor con JSON-LD | Leer el JSON-LD | S | Alta | Nicho, pero fácil. Su `robots.txt` bloquea solo perfiles y compras. |
| **[Beneficios de la diaria](https://beneficios.ladiaria.com.uy/category/espectaculos/)** | Espectáculos con **descuento para socios** de la diaria (2x1, entrada libre): teatro, música, Sodre, Zitarrosa, Planetario. Unos 10 por página, 9 páginas. | WordPress con firewall (la API REST está bloqueada) | **Feed RSS de la categoría** (`/category/espectaculos/feed/`). Cada ítem trae "Fecha y hora", "Lugar" y "Precio" en texto semiestructurado, más el enlace a la ticketera. El tipo de beneficio (2x1) está en el listado HTML. | S | Alta | Ver el detalle abajo. Su `robots.txt` solo bloquea las vistas de calendario, que no hacen falta. |
| [Vamos Eventos](https://www.vamoseventos.com) | Agregador de más de 100 ciudades: eventos, tours y experiencias | Next.js en Vercel con Supabase; checkpoint anti-bot de Vercel (429) | **No usar** (sus términos prohíben el scraping) | — | Baja | Ver el detalle abajo. Sirve como referencia y para ver qué fuentes existen. |
| Socio Espectacular | Revista mensual en PDF con cartelera teatral | PDF | Bajar el PDF, extraer el texto con `pdftotext` (gratis) y parsearlo con reglas | M | Baja | Una vez por mes; útil para validar. Sin LLM (por costo), el parseo es frágil: **opcional**. |
| Agendas de prensa (El Observador, la diaria, Montevideo Portal) | Selección semanal | HTML | Parseo de las notas | M | Baja | Texto libre y poco exhaustivo. Mejor como señal que como fuente. |
| [cine.com/uy](https://www.cine.com/uy/cartelera) | Cine | HTML | — | — | — | Redundante con Cine Uruguay. Descartar. |

### Beneficios de la diaria en detalle

Sirve para dos cosas:

- **Enriquecer eventos que ya tenemos.** Muchos ítems enlazan a RedTickets (por ejemplo `redtickets.uy/evento/LA-REBELION-DE-LA-CARNE-Sala-Cero/34406/`). El ID de RedTickets permite **deduplicar de forma exacta** y agregarle al evento un dato que ninguna otra cartelera muestra: *"2x1 para socios de la diaria"*.
- **Descubrir salas chicas** que no aparecen en otras fuentes, como Espacio Zorrilla, Arteatro o Sala Valle Inclán.

**Detalles a tener en cuenta:**

- La información es pública; para **usar** el beneficio hay que ser socio.
- Las fechas vienen en texto libre ("14, 15, 21, 22 de noviembre y 5, 6 de diciembre"), así que hace falta un parser de fechas en español. Es el mismo problema que con RedTickets.
- Trae eventos del interior (por ejemplo la Fiesta de la Leche en Cardal, Florida): filtrar por departamento.
- **Modelo de datos:** conviene un campo `beneficios` en el evento, con fuente, tipo y enlace. Así se pueden sumar otros clubes de beneficios más adelante.

### Vamos Eventos en detalle

Lo miré con el navegador, porque bloquea los requests automáticos con un checkpoint de Vercel.

- **Qué es**: un agregador "curado con IA" de eventos en más de 100 ciudades (en Uruguay: Montevideo, Salto, Maldonado y Treinta y Tres). La app para iOS y Android figura como "próximamente".
- **Cobertura en Montevideo**: este mes muestra **42 eventos**, bastante menos que nuestras fuentes (RedTickets sola tiene ~168 y Tickantel ~205). Sus enlaces llevan a RedTickets, así que al menos en parte scrapea las mismas ticketeras.
- **¿Hay paywall?** **No para quien mira:** todo lo que revisé se ve sin cuenta. "Iniciar sesión" es para usuarios y organizadores. Se financia con:
  - **organizadores**: "Plan Organizador" y "Organizer Pro" (planes pagos) y "Destacar un evento" (pago único);
  - **afiliados**: tours de **Viator** (por su API de partners) y experiencias de **Fever**, con comisión;
  - **publicidad**.

  Los organizadores pueden reclamar su evento ("¿Es tuyo? Reclama").
- **¿Es de código abierto?** **No.** El backend es privado (Supabase) y no encontré repositorio público.
- **¿Se puede usar como fuente?** **No.** Sus términos dicen explícitamente que no se puede "extraer, recopilar o recolectar datos" ni "usar herramientas automatizadas (bots, crawlers) sin permiso". Su `robots.txt` bloquea los crawlers de entrenamiento para "proteger el data moat".
- **Qué sí se puede aprender de Vamos**:
  - usa JSON-LD `Event` con coordenadas, buena práctica para SEO;
  - arma páginas por momento ("hoy", "esta noche", "este finde") y por categoría;
  - deja que los organizadores reclamen su evento.

---

## 3) Redes sociales

### Cuentas relevantes

| Cuenta | Seguidores (aprox.) | Notas |
|--------|---------------------|-------|
| [@hoyquehagomontevideo](https://www.instagram.com/hoyquehagomontevideo/) | 90-110 mil | La que mirás vos. **Lanzó su propia app** ([El Observador](https://www.elobservador.com.uy/cafe-y-negocios/la-uruguaya-que-empezo-publicar-planes-instagram-despues-la-pandemia-hoy-suma-mas-90000-seguidores-y-decidio-lanzar-su-propia-app-n6038228)): es referencia y también competencia directa. |
| Descubrí Montevideo (IG) | 60 mil | Publica la agenda semanal como imagen. |
| [@_quehacemoshoy](https://www.instagram.com/_quehacemoshoy/) | 9,7 mil | |
| [@_queplan](https://www.instagram.com/_queplan/) | 3,4 mil | Bares, planes y actividades LGBTQI+ friendly. |
| Intendencia de Montevideo | — | Anuncios oficiales; el portal de eventos ya trae casi todo estructurado. |
| Cuentas de salas chicas y cineclubes (`sala.ducon`, `salacamacua`, `kino_cineclub`…) | — | Muchas programan **solo** por Instagram. Cine Uruguay ya sigue unas 15. |

### Técnicas posibles

| Técnica | Cómo | Costo | Riesgo | Viabilidad |
|---------|------|-------|--------|------------|
| **Business Discovery de la Graph API** (oficial) | Con una cuenta de Instagram Business propia y una app de Meta, se leen los posts recientes (texto e imagen) de cuentas Business o Creator públicas | Gratis | Bajo. Tiene límites de uso, no funciona con cuentas personales y el proceso de aprobación es engorroso (**a verificar** si alcanza el modo desarrollo) | Media |
| Scrapers de terceros (Apify, HikerAPI) | Servicios pagos que leen perfiles públicos | ~US$ 1,5 cada 1.000 posts en Apify | Zona gris respecto a los términos de Meta; se rompen cuando Instagram cambia | Descartado (pago) |
| Instaloader (open source) | Librería de Python | Gratis | Bloqueos y límites agresivos; requiere sesión | Baja |

> **En pausa por costo** (decisión). La API oficial es gratis, pero la extracción buena del flyer necesita un LLM con visión, que es pago. La única vía sin costo es la API oficial más OCR libre (Tesseract) y reglas, con calidad bastante peor. Queda como posible fase futura.

**Después de bajar el post hay que extraer el evento.** La mayoría de los eventos vienen en un flyer, así que se necesita un LLM con visión (por ejemplo Claude) que lea la imagen y el texto. Tiene que devolver título, fecha, hora, lugar y precio en JSON, más un nivel de confianza. Cine Uruguay hace esto mismo con OCR.

**Ojo con las cuentas agregadoras** como @hoyquehago: republican eventos de otros. Conviene usarlas como **señal para descubrir** eventos, buscar la fuente original para el dato y no republicar sus imágenes ni sus textos.

**Esfuerzo: L.** Es lo que más mantenimiento pide y donde más se paga por evento, pero es lo único que trae la movida independiente.

---

## 4) Ticketeras

| Ticketera | Qué cubre | Tecnología | Técnica | Esfuerzo | Viabilidad | Notas |
|-----------|-----------|------------|---------|----------|------------|-------|
| **[Tickantel](https://tickantel.com.uy)** | Solís, Antel Arena, Sodre, salas IM, deporte, interior | Next.js | 1) `shows-sitemap.xml` lista **~205 espectáculos** activos. 2) Cada página trae un payload estructurado con `title`, `venue`, `date`, `fechaDesde`, `fechaHasta` y `fechaProxFuncion`. | S-M | **Alta** | El `robots.txt` lo permite y publica el sitemap. Incluye el interior (Teatro Macció en San José, Politeama en Canelones): **hay que filtrar por departamento**. La página no informa la categoría, y algunas funciones canceladas siguen como "programadas" en el JSON-LD: la cancelación se lee del aviso de cada función. |
| **[RedTickets](https://www.redtickets.uy)** | Salas chicas e independientes, bares, fiestas, MMB | GeneXus, HTML del servidor | **El catálogo completo está en la búsqueda paginada** (`/busqueda?,,,0,N`, 24 eventos por página, unos 800 eventos de todo el país). La portada y las categorías muestran solo una parte. El listado trae la categoría (permite descartar deportes y cursos sin abrir el detalle); el detalle `/evento/<slug>/<id>/` trae la ciudad, las funciones y la dirección. Un caché (`datos/cache/redtickets.json`) evita volver a abrir cada detalle más de una vez por día, y los eventos de otras ciudades, más de una vez por semana: la primera corrida tarda unos 13 minutos y las siguientes, 1 o 2. | M | **Alta** | El `robots.txt` lo permite. En la portada la fecha viene en texto ("Viernes 30 de Octubre"), pero **el detalle de cada evento trae las funciones estructuradas** (`Dates` → `Times` → `Tickets`, con fecha ISO, hora, agotado, precio, coordenadas y productor). También trae la **categoría** y la **ciudad** de cada evento, y los tipos de entrada muestran los **beneficios** ("2x1 La Diaria", "50% OFF Socio Espectacular"). Dice tener más de la mitad de los eventos del país. **No es RED UTS**: no lo afecta la compra de Ticketmaster. |
| **[Ticketmaster.uy](https://www.ticketmaster.uy)** | Conciertos internacionales grandes (desde agosto de 2026) | *Crowder* (la plataforma de Ticketmaster en Latinoamérica), HTML del servidor | La portada trae las *cards* en JSON con `title`, `description` (la fecha en texto) y `link` (`/event/<slug>`). El detalle trae **JSON-LD `Event`** con el lugar y la dirección. | S | **Alta** | Su `robots.txt` no restringe a los bots genéricos. **Mismo parser que All Access (Buenos Aires).** Hoy tiene pocos eventos (Foo Fighters 2027), pero va a crecer con los recitales grandes. Desde una IP de fuera de Uruguay daba 403. |
| [RED UTS](https://reduts.com.uy) | Eventos masivos (hoy casi nada) | Palco4, app JS con llamadas DWR | Navegador headless | M | Baja | Comprada por Ticketmaster; va a migrar a ticketmaster.uy. **No vale la pena.** |
| [Passline](https://www.passline.com) | Electrónica, fiestas, eventos chicos (Uruguay y Argentina) | App JS sobre una **API REST interna** (`api.passline.com/v1/...`) | Mapear los endpoints de eventos con el navegador y consumir la API | M | Media-Alta | Detecté la API, pero falta mapear qué endpoints traen los eventos. |
| Abitab | Variado; **entradas de Carnaval** en el Teatro de Verano | Cloudflare con desafío anti-bot (403 `cf-mitigated: challenge`) | **No scrapear** (sería saltearse un bloqueo). El dato tiene que salir del Teatro de Verano, del portal de la IM o de la productora. | — | Baja | |

---

## 5) Productoras

| Productora | Sitio | Tecnología | Técnica | Esfuerzo | Viabilidad | Notas |
|------------|-------|------------|---------|----------|------------|-------|
| **[Gaucho](https://www.gaucho.com.uy)** | `gaucho.com.uy/shows.php` | PHP simple, HTML del servidor | Parseo HTML | S | Alta | Hace **Primavera 0** y produjo a Roger Waters y Fito Páez. Anuncia Pixies y Los Redondos. Pocos eventos, pero **llegan antes que a la ticketera**. |
| **[AM Producciones](https://am.com.uy)** | `am.com.uy/articulos/shows` | Next.js | Payload de Next o HTML | S | Media-Alta | Jaime Roos, Rolling Stones, shows en el Centenario y el Antel Arena. Sigue trabajando con Ticketmaster. Junto con Gaucho, confirmó Foo Fighters para febrero de 2027. |
| **[Piano Piano](https://pianopiano.uy)** | `pianopiano.uy/agenda` (también `/fiestas`) | WordPress con tema propio; la API REST está desactivada, pero el HTML viene del servidor y hay sitemap | Parseo HTML de la agenda: título, fecha, lugar y enlace a RedTickets | S | Alta | Nació en 2018 con Cosquín Rock Uruguay. Hace La Vela Puerca, La Kermesse Redonda, los Harlem Globetrotters y obras en El Galpón, además de fiestas (Club de la Cumbia, Love the 90s). |
| Otras | — | — | — | — | — | Se suman de a poco. Las de electrónica y las independientes suelen estar solo en Instagram. |

**Para qué sirven:** detectar anuncios ("viene X en marzo") antes de que salgan las entradas. Después el mismo evento aparece en Tickantel, RedTickets o Ticketmaster.uy, así que **es obligatorio deduplicar**.

---

## 6) Buenos Aires: conciertos internacionales y festivales

> **Descartado por ahora (31/10/2026).** Queda la investigación por si se retoma.

| Fuente | Tipo | Resultado de la prueba | Técnica | Viabilidad |
|--------|------|------------------------|---------|------------|
| **[All Access](https://www.allaccess.com.ar)** | Ticketera de Live Nation (DF Entertainment): los shows internacionales grandes | 200, *Crowder* (igual que Ticketmaster.uy), con unas 49 *cards* de eventos en la portada | **Mismo parser que Ticketmaster.uy** | **Alta** |
| [Livepass](https://livepass.com.ar) | Ticketera (por ejemplo, Ed Sheeran 2026) | 200, HTML del servidor con JSON-LD | Leer el JSON-LD | **Alta** |
| [Lollapalooza Argentina](https://www.lollapaloozaar.com) | Festival (12-14 de marzo de 2027) | 200, HTML del servidor | Parseo HTML del line-up | Alta (bajo volumen) |
| [Cosquín Rock](https://cosquinrock.net) | Festival | 200, WordPress, HTML del servidor | API REST o HTML | Alta |
| [Primavera Sound BA](https://www.primaverasound.com/es/buenos-aires) | Festival (28-29 de noviembre de 2026) | 200, pero el contenido se arma con JS | Navegador headless o API interna | Media |
| [Movistar Arena](https://www.movistararena.com.ar) | Sala de conciertos | 200, **Blazor Server**: los datos llegan por websocket, no por una API | Navegador headless (Playwright) | Media |
| [Enigma](https://www.enigmatickets.com) (por ejemplo, Alejandro Sanz), [Tu Entrada](https://www.tuentrada.com) | Ticketeras | 200, app JS | API interna o headless | Media |
| Personal Fest, Quilmes Rock, BA Trap | Festivales | No encontré el dominio | A verificar | — |
| Ticketmaster Argentina | — | El dominio `ticketmaster.com.ar` no existe; en Argentina, Live Nation vende por All Access | — | — |
| Songkick, Bandsintown, Resident Advisor | Agregadores de conciertos | **403 / 406** también desde Uruguay (anti-bot real) | Bandsintown da API solo por convenio. La API de Songkick históricamente no da keys nuevas (a verificar) | Baja |

**Recomendación:** acotar el alcance. Por ejemplo: **solo festivales más artistas internacionales en estadios y arenas** (River, Vélez, Movistar Arena, Hipódromo, Costanera Sur). Son pocas decenas de eventos por año. Alcanza con:

- **All Access** (reusando el parser de Ticketmaster.uy) y **Livepass**, filtrados por sala,
- un scraper por festival (S cada uno, revisado una vez por semana),
- Movistar Arena con headless, si hace falta.

---

## 7) Walking tours y experiencias

### Cómo modelarlos

Los tours no se comportan como un recital: hay dos tipos y conviene tratarlos distinto en el modelo de datos.

- **Con fecha**: por ejemplo "Misterios del Salvo - Noviembre" de Peatonal Tours, o un recorrido de la IM con inscripción. Entran a la cartelera como cualquier evento.
- **Recurrentes o permanentes**: por ejemplo la entrada general al Castillo Pittamiglio, un tour de Peatonal Tours que se repite todos los meses o un "Recorrido libre por el Teatro Solís". Van en una sección tipo **"Siempre disponible / Experiencias"**, con días y horarios, y no se repiten como evento en cada fecha.

### Fuentes

| Fuente | Qué tiene | Tecnología | Técnica | Esfuerzo | Viabilidad | Notas |
|--------|-----------|------------|---------|----------|------------|-------|
| **[RedTickets, categoría Turismo](https://www.redtickets.uy/categoria/32/Turismo)** (y [Museos](https://www.redtickets.uy/categoria/45/Museos)) | **23 actividades hoy**: Peatonal Tours, visitas guiadas al Palacio Salvo, Castillo Pittamiglio, Bus Turístico "Descubrí Montevideo", Reserva Natural Salus, Bodega Santa Rosa, Plaza de Toros de Colonia | Igual que el resto de RedTickets; en estas páginas el campo se llama `Title` | **Reusar el scraper de RedTickets** filtrando por categoría | S (sale casi gratis) | **Alta** | Hay que **filtrar**: lo que está fuera de Montevideo (Colonia, Carmelo) y lo pensado para turistas (Bus Turístico "NO RESIDENTES", vuelos panorámicos). |
| **[Peatonal Tours](https://www.peatonaltours.uy)** | Tours temáticos pensados para el público local (Misterios de la Ciudad Vieja, Crímenes y tragedias, Paseo Bello & Reborati, Descubrí tu barrio, Misterios del Salvo), con punto de encuentro, duración y precio (UYU 500-600) | Next.js, HTML del servidor | Parseo HTML de la portada y de `/booking`. Las fechas concretas salen de **RedTickets**. | S | Media-Alta | **El modelo de lo que buscamos.** También tiene Instagram (@peatonaltours). |
| **Portal de eventos IM, categoría "Paseos"** | Recorridos gratuitos de la IM (por ejemplo "Recorrido libre por el Teatro Solís", "Paseo Sur Palermo", tours por el Parque Rodó con inscripción) | JSON:API (`field_categoria` = Paseos) | **Reusar el scraper del portal IM** filtrando por categoría | S | **Alta** | Hoy hay pocos: 3 actividades y 1 evento. Los recorridos de temporada se anuncian por tandas. |
| Caminatas barriales del BPS e IM | Recorridos a pie para personas mayores (convenio BPS-IM) | Páginas de bps.gub.uy | Parseo HTML | S | Media | Público específico; opcional. |
| Visitas guiadas en edificios | Teatro Solís, **Palacio Salvo**, Palacio Legislativo, Castillo Pittamiglio, Torre de Antel | Varios | El Salvo y el Castillo ya entran por RedTickets; el Solís, por el portal IM. El resto, a verificar sitio por sitio | S-M | Media | |
| Instagram de colectivos y guías locales | Recorridos barriales, caminatas temáticas y de memoria, tours de grupos chicos | Instagram | La misma técnica que la sección 3 | L | Media-Baja | Muchos guías locales solo publican ahí. **¿Conocés cuentas?** |
| **Eventos anuales con muchos recorridos** | **Día del Patrimonio** (primer finde de octubre, más de 500 actividades en el país), **Museos en la Noche** (diciembre), **Montevideo + Museos** (mayo) | Guías en gub.uy, a menudo en PDF | Scraper o extracción por LLM **una vez por año**, cuando se publica la guía | M (por evento) | Media | Mucho volumen en un solo finde: vale la pena una página especial. |

### Descartadas (orientadas a turistas extranjeros)

| Fuente | Por qué se descarta |
|--------|---------------------|
| Viator, GetYourGuide, Civitatis | Tours pagos para visitantes (city tours, excursiones para cruceros, bodegas). Además, su modelo es de afiliados con comisión. |
| GuruWalk, freetour.com | Free tours de plataformas internacionales, pensados para quien visita la ciudad (Ciudad Vieja en inglés y portugués). Técnicamente son fáciles (JSON-LD), así que se pueden retomar si aparece algún tour con enfoque local. |
| Audioguías (Navaway / Ryo) | No son eventos. |

**Recomendación:** los tours locales suman mucho y cuestan poco. RedTickets Turismo (Peatonal Tours, Palacio Salvo, Castillo Pittamiglio) y la categoría Paseos de la IM salen casi gratis con los scrapers de la fase 1. Peatonal Tours y los eventos anuales (Día del Patrimonio, Museos en la Noche) se suman con poco esfuerzo.

---

## 8) Museos y exposiciones (exploración del 31/10/2026)

Oferta de museos de arte e historia. Lo que publican son sobre todo **exposiciones** (con fecha de inauguración y de cierre, y horario de la sala) y **actividades** (visitas guiadas, talleres, charlas) con fecha. Las exposiciones irían en el rubro Exposiciones y, como duran semanas, en "Ver propuestas con muchas fechas".

| Fuente | Qué tiene | Tecnología | Técnica | Esfuerzo | Viabilidad |
|--------|-----------|------------|---------|----------|------------|
| **Museos de la Intendencia** ([Cabildo](https://cabildo.montevideo.gub.uy), [Subte](https://subte.montevideo.gub.uy), [MUMI](https://mumi.montevideo.gub.uy), Blanes) | Exposiciones actuales (`/exposiciones`) y eventos por mes (`/eventos/mes/2026-10`, `/evento/<slug>`) | Drupal 7, la misma plataforma para todos | **Un parser para todos** | S-M | **Alta** |
| [MNAV](https://mnav.gub.uy) | Exposiciones actuales, próximas y pasadas; actividades con fecha y hora ("Miércoles 04 de Nov, 2026. 16:30 h") | PHP propio (`cms.php?id=…`), HTML del servidor | Parseo HTML | S | Alta |
| [Calendario de actividades del MEC](https://www.gub.uy/ministerio-educacion-cultura/comunicacion/calendario-actividades) | Actividades de los museos nacionales (MNAV, Histórico, Figari…) y más (Sodre, Ballet), de todo el país | Drupal (gub.uy), HTML del servidor, paginado | Parseo HTML del listado y de cada ficha, filtrando Montevideo | M | Media-Alta |
| [Museo Torres García](https://www.torresgarcia.org.uy/exposiciones.php) | Exposiciones actuales y futuras | HTML simple | Parseo HTML | S | Alta |
| [Museo Gurvich](https://museogurvich.org), [MAPI](https://mapi.uy) | Muestras y actividades | WordPress (sin tipo de evento en la API) | HTML de las novedades | M | Media |
| [Museo del Carnaval](https://www.museodelcarnaval.org) | Agenda | WordPress con The Events Calendar: API `/wp-json/tribe/events/v1/events` | Leer la API | S | Alta (hoy, sin eventos cargados) |
| [Portal de Museos del Uruguay](https://museos.gub.uy) | Directorio de museos por departamento | Joomla | Sirve para el catálogo de salas, no tiene agenda | — | — |
| Montevideo + Museos (mayo) y Museos en la Noche (diciembre) | Jornadas anuales con decenas de espacios | Guías en PDF; parte llega al portal IM | Si la IM los carga en su portal, entran solos | — | Media |

**Hecho (31/10/2026):** Cabildo, Subte, MNAV, Torres García, Gurvich (exposiciones con período y la agenda de la portada), MAPI (exposiciones actuales, sin fecha de cierre) y el calendario del MEC (solo actividades en museos de Montevideo: se descartan las virtuales y las de otros departamentos). **Queda:** el Blanes y el MUMI, si ordenan sus páginas. Todo lo que viene de estas fuentes lleva la etiqueta **Museos**. Para no llenar la agenda, cada exposición se muestra una vez (en "Con muchas fechas · en exhibición") con su período y horario, no como una función por día.

---

## Técnicas transversales

### Niveles de técnica (de más estable a menos)

1. **API JSON pública o interna** (portal IM, Sodre, Zitarrosa, Passline). Estable, barata y sin parseo de HTML.
2. **Datos estructurados embebidos en el HTML** (JSON-LD en Ticketmaster.uy, Livepass y Fever; payload de Next.js en Tickantel; objetos JSON en RedTickets y en las *cards* de Crowder). Casi igual de estable.
3. **Sitemaps** para descubrir URLs (Tickantel, Sodre, El Galpón). Sirven para ver qué hay de nuevo sin recorrer todo el sitio.
4. **Parseo HTML clásico** (Solís y Teatro de Verano, Cartelera, Galpón). Se rompe cuando cambia el diseño: necesita tests y alertas.
5. **Navegador headless** (Playwright) para sitios que solo cargan con JS (Movistar Arena, Primavera Sound). Más lento y caro; usarlo solo si no aparece una API interna.
6. **Imagen más LLM** (flyers de Instagram, PDFs). **Descartado por costo**; la alternativa gratis es OCR libre (Tesseract), con menos calidad.

### Reglas de buen comportamiento

- Respetar `robots.txt` y usar un User-Agent propio e identificable (por ejemplo `CarteleraMVD/0.1 (+contacto)`).
- **No saltear desafíos anti-bot** (Cloudflare, CAPTCHAs). Si un sitio bloquea, se descarta o se busca el dato en otra fuente.
- Frecuencia baja: una o dos veces por día alcanza para una cartelera; los festivales, una vez por semana.
- No republicar imágenes ni textos largos de terceros: guardar el dato y **linkear a la fuente** para comprar la entrada.
- No consumir el trabajo de otros agregadores (Cine Uruguay, @hoyquehago, Vamos) sin su permiso.

### Deduplicación (crítica)

El mismo evento puede llegar por Tickantel, la web de la sala, la Cartelera, el portal IM y la productora. Hace falta:

- normalizar sala (un catálogo propio de lugares con alias: "Auditorio Adela Reta" = "Auditorio Nacional del Sodre"). Los `node--lugar` del portal IM, que vienen con coordenadas, son un buen punto de partida;
- normalizar fecha y hora (zona `America/Montevideo`);
- comparar títulos de forma difusa (sin tildes, sin "presenta:", etc.);
- fusionar los registros guardando **todas las fuentes** de cada evento y una prioridad para elegir qué dato mostrar.

### Infraestructura

- **Todo tiene que entrar en planes gratuitos.** Opciones razonables:
  - **Scrapers**: GitHub Actions con un cron diario (gratis en repos públicos).
  - **Datos**: un JSON versionado en el mismo repo, o la capa gratuita de Supabase.
  - **Web**: GitHub Pages, Vercel o Netlify en su plan gratis.
- **Desde dónde corren los scrapers importa.** Desde una IP de fuera de Uruguay, Ticketmaster.uy y All Access daban 403 y los sitios de la IM no respondían; desde Uruguay andan. GitHub Actions corre en EE. UU., así que **hay que probar si estos sitios aceptan sus IPs** antes de decidir. Si no, la alternativa sin costo es correr los scrapers en una máquina propia en Uruguay (una compu o una Raspberry Pi con cron) y publicar desde ahí.
- **Prueba de conectividad**: [`scripts/check-fuentes.sh`](../scripts/check-fuentes.sh) pide cada fuente de las fases 1 a 3 con dos User-Agent (uno propio e identificable y uno de navegador) y verifica que la respuesta traiga el dato esperado. El workflow [`check-fuentes.yml`](../.github/workflows/check-fuentes.yml) corre el mismo script en GitHub Actions.
  - **Desde Uruguay (30/10/2026): 19 de 19 fuentes OK, también con el User-Agent propio.**
  - **Desde GitHub Actions (IP de EE. UU., 30/10/2026): 15 de 19 OK.** Fallan con los dos User-Agent:

    | Fuente | Error | Probable causa |
    |--------|-------|----------------|
    | Portal de eventos IM | timeout | La infraestructura de la IM no responde a IPs de fuera de Uruguay (igual que desde otras IPs de afuera) |
    | Sala Zitarrosa | timeout | Idem (subdominio de la IM) |
    | Ticketmaster.uy | 403 | La plataforma Crowder bloquea IPs extranjeras o de datacenter |
    | All Access | 403 | Idem (misma plataforma) |

    El Teatro de Verano, aunque es un subdominio de la IM, sí respondió.

### Arquitectura resultante: híbrida y sin costo

- **GitHub Actions** corre las 15 fuentes que responden (todas las demás del MVP) y publica la web.
- **Un equipo local en Uruguay corre las bloqueadas** (decisión del 30/10/2026): el portal IM, la Zitarrosa y Ticketmaster.uy.
- **Se usa una tarea programada del sistema**, **no un runner self-hosted de GitHub**:
  - **Seguridad:** el repo es público, y GitHub desaconseja runners self-hosted en repos públicos, porque un pull request de un tercero podría ejecutar código en la máquina.
  - **Reposo:** si el equipo estaba dormido a la hora programada, la tarea corre apenas se despierta. Un runner, en cambio, deja el job en cola y GitHub lo cancela a las 24 horas.
  - **La tarea** corre sus scrapers, guarda el JSON y hace `git push`. Después, GitHub Actions arma la web con todo junto.
- **Horario**: días de semana a las 11 h.
- **Fines de semana**: esas fuentes quedan con el dato del viernes. No es grave, porque los eventos del finde ya se scrapearon antes.
- **Cada fuente guarda su último resultado bueno**, para que una caída, un bloqueo o el equipo apagado no vacíen la cartelera.
- **Más adelante**, el mismo job se puede pasar a otro equipo (una compu vieja con Linux o una Raspberry Pi) sin cambiar el código.
- **Lo que más importa del runner local es el portal IM** (eventos municipales y gratuitos). Ticketmaster.uy tiene pocos eventos, y la Zitarrosa en parte vende por Tickantel.
- **El repo es público** (desde el 30/10/2026): GitHub Actions no tiene límite de minutos y **GitHub Pages es gratis**, así que scrapers y web pueden vivir en el mismo repo sin costo.
- **Portal IM**: hay que filtrar siempre por `filter[status]=1`; si no, la API devuelve ítems despublicados vacíos ("insufficient authorization").
- Guardar el HTML o JSON crudo de cada corrida durante unos días: ayuda muchísimo a depurar cuando un parser se rompe.

---

## Plan sugerido por fases

| Fase | Fuentes | Qué se logra |
|------|---------|--------------|
| **1. MVP** | **Ticketeras**: Tickantel, RedTickets, Ticketmaster.uy. **Carteleras**: portal de eventos IM (JSON:API, solo eventos), Cartelera de Montevideo Portal (teatro). **Salas**: Sodre y Zitarrosa (API WP), Solís y Teatro de Verano (parser compartido), El Galpón. **Cine**: Cinemateca. Todo filtrado a Montevideo. | La gran mayoría de la cartelera visible, lo municipal y el cine de Cinemateca, con fuentes estables y sin costo |
| 2 | Gaucho, AM, Piano Piano, beneficios de la diaria, Sala del Museo, Teatro Circular, Fever, Passline. **Tours**: RedTickets Turismo, eventos de la categoría Paseos de la IM, Peatonal Tours, Día del Patrimonio y Museos en la Noche | Anuncios tempranos, más salas y la sección de walking tours locales |
| En pausa | Instagram, Socio Espectacular | Requieren LLM para andar bien, y eso tiene costo |
| Descartado por ahora | Buenos Aires: All Access, Livepass, festivales, Movistar Arena | Decisión del 31/10/2026 |

---

## Preguntas abiertas para vos

Ninguna por ahora. Las últimas (otros guías de tours locales y otros clubes de beneficios) quedaron en "no, por ahora".

---

## Fuentes consultadas

- Ticketmaster en Uruguay y RED UTS: [Ticketmaster Business](https://business.ticketmaster.com/press-release/ticketmaster-in-uruguay/), [Forbes Uruguay](https://www.forbesuruguay.com/negocios/ticketmaster-adquiere-red-uts-llega-pais-uruguay-era-nuestro-proximo-paso-estrategia-expansion-dijo-market-leader-n94712), [Búsqueda](https://www.busqueda.com.uy/vida-cultural/ticketmaster-desembarca-uruguay-y-apuesta-un-mercado-mas-recitales-grandes-n5415951), [IQ Magazine](https://www.iqmagazine.com/2026/08/ticketmaster-scoops-up-red-uts-amid-uruguay-entry/), [Rio Times](https://www.riotimesonline.com/ticketmaster-lands-uruguay-concerts-2026/)
- Piano Piano: [pianopiano.uy/agenda](https://pianopiano.uy/agenda), [Empresas & Eventos](https://empresasyeventos.com.uy/index.php/2024/08/16/piano-piano-y-3-cuartos-expertos-en-produccion/), [Montevideo Portal](https://www.montevideo.com.uy/Tiempo-libre/Piano-Piano-anuncia-una-temporada-record-en-Punta-del-Este-y-proyecta-su-agenda-2026-uc946689)
- Beneficios de la diaria: [Espectáculos](https://beneficios.ladiaria.com.uy/category/espectaculos/)
- Gaucho y AM: [gaucho.com.uy/nosotros](https://www.gaucho.com.uy/nosotros.php), [am.com.uy/articulos/shows](https://www.am.com.uy/articulos/shows), [El Observador sobre Foo Fighters](https://www.elobservador.com.uy/cultura-y-espectaculos/foo-fighters-se-presentara-uruguay-la-pista-la-productora-que-confirmo-la-visita-n6052471)
- Antel Arena: [la diaria](https://ladiaria.com.uy/politica/articulo/2025/10/antel-arena-pasara-a-ser-gestionado-por-una-subsidiaria-de-la-empresa-estatal-y-estiman-un-ahorro-de-cerca-de-500000-dolares-anuales/)
- Abitab y Carnaval: [Montevideo Portal](https://www.montevideo.com.uy/Tiempo-libre/Comenzo-la-venta-de-entradas-para-Carnaval-en-el-Teatro-de-Verano-precios-y-donde-comprar-uc950737)
- Hoy qué hago: [la diaria (2021)](https://ladiaria.com.uy/cotidiana/articulo/2021/7/hoy-que-hago-una-aplicacion-le-lleva-la-agenda-a-montevideo/), [El Observador (2026)](https://www.elobservador.com.uy/cafe-y-negocios/la-uruguaya-que-empezo-publicar-planes-instagram-despues-la-pandemia-hoy-suma-mas-90000-seguidores-y-decidio-lanzar-su-propia-app-n6038228)
- Cine Uruguay: [cineuruguay.com/acerca](https://cineuruguay.com/acerca/)
- Teatro Circular: [Montevideo Portal sobre la inundación](https://www.montevideo.com.uy/Noticias/-Con-una-angustia-tremenda--historico-teatro-de-Montevideo-sufrio-una-grave-inundacion-uc937955)
- Primavera Sound BA 2026: [mxdwn](https://music.mxdwn.com/2026/05/11/news/primavera-sound-buenos-aires-sao-paulo-2026-lineups-announced-featuring-gorillaz-the-strokes-fka-twigs-more/amp/), [Stereoboard](https://www.stereoboard.com/primavera-sound-buenos-aires-tickets/buenos-aires/2026-11-28)
- DF Entertainment y Live Nation: [iProfesional](https://www.iprofesional.com/negocios/283658-El-mayor-productor-mundial-de-espectaculos-desembarca-en-la-Argentina)
- Ticketeras en Argentina: [IQ International Ticketing Report 2025](https://www.iqmagazine.com/publications/international-ticketing-report-2025/southern-cone/), [Ed Sheeran Argentina 2026 (FAQ)](https://www.edsheeran.com/sites/g/files/g2000021856/files/2026-04/Ed%20Sheeran%20ARG%202026%20-%20FAQs_cdadw23ds.pdf), [A24 sobre Alejandro Sanz](https://www.a24.com/primiciasya/musica/alejandro-sanz-argentina-2026-precios-y-como-comprar-las-entradas-n1477088/amp)
- APIs de Instagram: [referencia de APIs oficiales (abril de 2026)](https://gist.github.com/jameschapman2c/65eff9f54a2d350b17a6ce5127b9fe42), [comparativa de scrapers](https://www.socialcrawl.dev/blog/instagram-scraping-2026)
- Bandsintown API: [centro de ayuda](https://help.artists.bandsintown.com/en/articles/7053475-api-and-app-id)
- Vamos Eventos: [Montevideo este mes](https://www.vamoseventos.com/montevideo/este-mes), [términos](https://www.vamoseventos.com/es/terms)
- Walking tours: [Peatonal Tours](https://www.peatonaltours.uy/), [Peatonal Tours en Descubrí Montevideo](https://www.descubrimontevideo.uy/peatonal-tours-una-propuesta-de-trip-uruguay), [tours gratuitos de la IM en el Parque Rodó](https://www.montevideo.com.uy/Tiempo-libre/Tours-gratuitos-por-Montevideo-en-abril-recorridos-guiados-por-el-Parque-Rodo-uc958577), [caminatas barriales del BPS](https://www.bps.gub.uy/24259/caminatas-barriales.html)
- Eventos anuales: [Día del Patrimonio 2026](https://www.gub.uy/presidencia/comunicacion/noticias/dia-del-patrimonio-2026-cuando-es-convocatoria-raices-indigenas), [Museos en la Noche](https://www.gub.uy/ministerio-educacion-cultura/comunicacion/noticias/museos-noche-celebra-su-edicion-bicentenario), [Montevideo + Museos](https://www.gub.uy/ministerio-turismo/comunicacion/noticias/se-desarrolla-nueva-edicion-montevideo-museos)
