# Apify Schema · Instagram (`apify/instagram-scraper`)

Mapeo del shape real que devuelve el actor `apify/instagram-scraper` (Act ID `shu8hvrXbJbY3Eb9W`), validado contra el dataset `QPFngkHiDgeV8gZka` (run del 03-may-2026, 100 items).

## Item shape (un objeto por publicación)

| Campo | Tipo | Descripción | Uso en transform |
|---|---|---|---|
| `id` | string | ID único de la publicación (numérico largo) | join key |
| `type` | `"Image" \| "Video" \| "Sidecar"` | Tipo de publicación. Sidecar = carrusel | `by_type` aggregation |
| `shortCode` | string | Código corto de la URL (`DXxLhLi…`) | construir URL si falta |
| `caption` | string | Texto de la publicación | hashtags + captions_avg_len |
| `hashtags` | array<string> | Hashtags extraídos del caption (sin `#`) | `top_hashtags` |
| `mentions` | array<string> | @usuarios mencionados (sin `@`) | — |
| `url` | string | URL completa al post | `top5.url` |
| `commentsCount` | number | Comentarios totales | engagement |
| `firstComment` | string | Primer comentario público | — |
| `latestComments` | array | Últimos comentarios capturados | — |
| `dimensionsHeight` | number | Alto del media en px | — |
| `dimensionsWidth` | number | Ancho del media en px | — |
| `displayUrl` | string | URL del thumbnail (CDN Instagram) | descargar a assets/thumbs/ |
| `images` | array | Si Sidecar, lista de imágenes adicionales | — |
| `alt` | string\|null | Texto alternativo | — |
| `likesCount` | number | Likes totales | engagement |
| `timestamp` | string ISO 8601 | Fecha y hora UTC de publicación | `by_day`, `by_hour`, `by_week` |
| `childPosts` | array | Posts hijos si es Sidecar | — |
| `ownerFullName` | string | Nombre del autor | — |
| `ownerUsername` | string | Handle del autor | join con cuenta |
| `ownerId` | string | ID numérico del autor | — |
| `isPinned` | boolean | Si está fijado en el perfil | — |
| `isCommentsDisabled` | boolean | Si tiene comentarios deshabilitados | — |
| `metaData` | object | **Perfil completo de la cuenta**, embebido en cada item | `accounts.Instagram` |
| `inputUrl` | string | URL que se pasó al actor como input | trazabilidad |

## metaData (perfil de la cuenta)

Cada item incluye `metaData` con el snapshot de la cuenta al momento del scrape. Tomamos del primer item (cualquiera vale, son idénticos):

| Campo | Tipo | Uso |
|---|---|---|
| `followersCount` | number | `accounts.Instagram.seguidores` |
| `followsCount` | number | `accounts.Instagram.siguiendo` |
| `postsCount` | number | `accounts.Instagram.posts_totales` |
| `biography` | string | `accounts.Instagram.bio` |
| `fullName` | string | `accounts.Instagram.nombre` |
| `businessCategoryName` | string | `accounts.Instagram.categoria` |
| `isBusinessAccount` | boolean | `accounts.Instagram.business_account` |
| `verified` | boolean | `accounts.Instagram.verified` |
| `externalUrl` | string | `accounts.Instagram.url_externa` |
| `profilePicUrl` | string | — (no se usa) |
| `businessAddress.street_address` | string | `accounts.Instagram.direccion` |
| `latestIgtvVideos` | array | — (no se usa para reportería actual) |

## Cálculo del engagement (engagement_post)

Para esta cuenta el engagement de cada post se calcula como:

```
engagement = likesCount + commentsCount
```

(No incluimos `shares` porque Instagram no los expone públicamente.)

## Agregaciones que produce el transformer

A partir de los 100 items se calculan:

```python
{
  "n_posts": 79,                  # solo posts con timestamp dentro de la ventana
  "engagement_total": 9195,
  "engagement_promedio": 116.4,
  "engagement_mediana": 29,
  "by_type": {
    "labels": ["Image", "Sidecar", "Video"],
    "counts": [14, 14, 51],
    "engagement": [1905, 517, 6773],
    "engagement_promedio": [136.1, 36.9, 132.8],
  },
  "by_day": {
    "labels": ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"],
    "counts": [...],
    "engagement_promedio": [...],
  },
  "by_hour": {
    "labels": ["8","9","10",...,"21"],  # horas con posts
    "counts": [...],
  },
  "by_week": {
    "labels": ["2026-S06","2026-S07",...],
    "counts": [...],
    "engagement": [...],
  },
  "top_hashtags": [["DíaDeLaMujer", 2], ...],   # tuplas (tag, n_apariciones), top 10
  "captions_avg_len": 152.0,
  "top5": [
    {
      "fecha": "2026-02-10",
      "tipo": "Video",
      "url": "https://www.instagram.com/p/.../",
      "media_url": "assets/thumbs/ig-<hash>.jpg",
      "caption": "...",
      "engagement": 3246,
      "likes": 3037,
      "comentarios": 209,
    },
    ...
  ],
}
```

## Notas operacionales

- **Limit del actor**: configurado a 100 items por run en `config/clients/comapan.yaml`. Para Comapan al ritmo actual eso cubre ~3 meses; suficiente para reportería quincenal con ventana 90d.
- **Costo por run**: ~$0.08 USD (a $2.70 / 1k results).
- **Tiempo típico de run**: ~58 segundos.
- **Thumbnails**: el `displayUrl` apunta al CDN de Instagram con URLs firmadas que expiran. El pipeline las descarga inmediatamente y guarda con nombre estable `ig-<sha1[10]>.jpg` en `assets/thumbs/`.
- **Posts fuera de ventana**: el actor retorna los últimos N (por fecha). El transform filtra por `timestamp` dentro de la ventana del periodo y descarta el resto.

## Caveats

- El campo `latestIgtvVideos` dentro de `metaData` puede tener data antigua (de 2021–2022). **Ignorarlo** para el reporte; solo usamos los items de nivel raíz.
- El `playCount` / `videoViewCount` NO está en este actor para reels. Si se requiere, considerar agregar `apify/instagram-reel-scraper` adicional.
- El actor scrapea desde HTML público; Instagram puede cambiar la estructura sin aviso. Si hay un mes con n_posts=0 inesperado, verificar status del actor en Apify console.

## Fixture de referencia

Una muestra del raw response real (anonimizada — URLs CDN truncadas) vive en:
`tests/fixtures/apify_instagram_2026-05-03.json`

Esa fixture se usa en los tests de `pipeline/transform/normalize.py` para asegurar que cualquier cambio futuro no rompa el shape canónico.
