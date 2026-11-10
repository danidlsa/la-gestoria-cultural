# Archivo

Cosas que se hicieron y se sacaron del sitio por ahora, guardadas para retomarlas.

## Tarjeta para compartir en Instagram (`tarjeta-para-compartir.patch`)

Archivada el 9/11/2026. El botón "Compartir" de cada evento abría un menú con tres opciones: el texto de siempre, una
imagen para historia (1080×1920) o una para posteo (1080×1350). La imagen era la tarjeta del evento sobre el fondo
cobalto, con la marca y el flyer.

**Por qué se archivó:** el navegador solo deja meter el flyer en una imagen nueva si el sitio de origen lo autoriza.
Para eso se pasaba por wsrv.nl, que anda con Sodre, Solís, Galpón, Tickantel y otros, pero no con RedTickets ni con
los sitios de la Intendencia (no responden fuera de Uruguay). Esos eventos salían sin flyer, con un bloque de color.

**Ideas que quedaron:** que los flyers de RedTickets se guarden en el propio sitio al armarlo (como los de "Agregá
tu evento"), o una vista a pantalla completa para sacarle captura.

**Para volver a ponerla**, desde la carpeta del repo:

```bash
git apply docs/archivo/tarjeta-para-compartir.patch
```

Toca `app.js`, `estilos.css`, la política de contenido de `index.html.j2` (permite pedir imágenes a wsrv.nl y a
Tickantel) y el párrafo de privacidad de `que-es.html.j2`. Si esos archivos cambiaron mucho desde entonces, puede
que haya que aplicarla a mano.
