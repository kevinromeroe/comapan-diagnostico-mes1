# Apify Schemas · Facebook

Mapeo de los dos actores que usamos para Facebook.

---

## `apify/facebook-posts-scraper` (Act ID `KoJrdxJCTtpon81KY`)

Devuelve un objeto por publicación. Dataset de referencia: `N9GarslS5N6kBaSSh`.

### Campos relevantes

| Campo | Tipo | Uso en transform |
|---|---|---|
| `postId` | string | join key |
| `url` | string | `top5.url` |
| `topLevelUrl` | string | URL canónica del post |
| `time` | string ISO 8601 | `by_day`, `by_week`, `by_hour` |
| `timestamp` | number (unix) | redundante con `time` |
| `pageName` | string | filtro de propiedad |
| `text` | string | caption — captions_avg_len + hashtags |
| `likes` | number | engagement |
| `shares` | number | engagement |
| `topReactionsCount` | number | total de reacciones (like + others) |
| `reactionLikeCount` | number | desglose reacciones |
| `reactionCareCount` | number | desglose reacciones |
| (otras `reaction*Count`) | number | love, haha, wow, sad, angry |
| `media[].thumbnail` | string | URL del thumbnail (CDN FB) |
| `media[].__typename` | string | "Photo", "Video", "Album" — equivale a `tipo` |
| `media[0].url` | string | URL del media (display) |
| `user.name` | string | autor |
| `user.id` | string | autor id |
| `facebookId` | string | id de la página |
| `inputUrl` | string | URL del input (trazabilidad) |

### Engagement formula

```
engagement = likes + shares + (commentsCount si aparece)
```

Caveat: Facebook Posts Scraper a veces NO incluye comentarios en el output. Si no aparece, usar `topReactionsCount + shares` y dejar nota en log.

### Caveat de fechas

Algunos posts antiguos vienen sin `time`. El transform debe filtrar esos hacia un counter `fb_undated` separado y NO incluirlos en `by_day`/`by_week`/`by_hour`. Solo `fb_total` los cuenta para indicar volumen real.

### Tipo de publicación

El campo `__typename` dentro de `media[0]` indica el tipo. Mapeo al shape canónico:

| `__typename` | `tipo` canónico |
|---|---|
| `Photo` | "Photo" |
| `Video` | "Video" |
| `Album` | "Album" |
| (sin media) | "Text" |

---

## `apify/facebook-pages-scraper` (Act ID `4Hv5RhChiaDk6iwad`)

Devuelve un objeto por página, con metadata completa. Dataset de referencia: `19FXfW393UvQltMHs`.

### Campos relevantes (un solo item por run)

| Campo | Tipo | Uso |
|---|---|---|
| `pageId` | string | id de la página |
| `pageName` | string | handle (e.g. "ComapanCo") |
| `title` | string | nombre mostrado |
| `categories` | array<string> | `accounts.Facebook.categoria` (join con coma) |
| `category` | string | categoría principal |
| `likes` | number | `accounts.Facebook.page_likes` |
| `followers` | number | seguidores (en FB suele coincidir con likes) |
| `followings` | number | a cuántos sigue la página |
| `address` | string | `accounts.Facebook.direccion` |
| `phone` | string | `accounts.Facebook.telefono` |
| `email` | string | — |
| `website` | string | `accounts.Facebook.website` |
| `rating` | string | `accounts.Facebook.rating` (e.g. "88% recommend (89 Reviews)") |
| `ratingOverall` | number | numérico (0-100) |
| `ratingCount` | number | cantidad de reviews |
| `intro` | string | descripción corta |
| `info` | array<string> | descripción larga (varias líneas) |
| `profilePictureUrl` | string | — |
| `coverPhotoUrl` | string | — |
| `ad_status` | string | indica si la página corre ads |
| `creation_date` | string | fecha de creación de la página |

### Nota operacional

Como el actor devuelve UN solo item, el extractor toma `items[0]` y rellena `accounts.Facebook` del shape canónico.
