# Apify Schemas · TikTok

## Actor activo — `clockworks/tiktok-profile-scraper`

- **ID:** `0FXVyOXXEmdGcV88a`
- **Costo:** $0.004 USD por resultado (pay-per-event, tier free)
- **Dataset típico:** ~50 items por corrida

Este es el **único actor de TikTok que se usa desde el 2026-07-21**. Retorna cuenta (perfil) + posts (videos) en un mismo dataset. Reemplaza al actor de "posts-scraper" que se descartó (ver sección Deprecated).

### Input mínimo

```yaml
profiles: ["comapanco"]
```

### Output — nivel item (video)

Cada item del dataset representa un video del perfil. Campos relevantes:

| Campo | Tipo | Uso |
|---|---|---|
| `id` | string | join key en Supabase |
| `webVideoUrl` | string | URL pública del video (`top5.url`) |
| `text` | string | caption — usa para captions_avg_len + hashtags |
| `createTime` | number (unix) | redundante |
| `createTimeISO` | string ISO 8601 | usa para `by_day`, `by_week`, `by_hour` (parsear como UTC) |
| `diggCount` | number | **likes** |
| `commentCount` | number | comentarios |
| `shareCount` | number | shares |
| `playCount` | number | visualizaciones (views) |
| `collectCount` | number | guardados (saves) |
| `hashtags` | array<object> | `[{id, name, title, cover}]` → tomar `name` |
| `videoMeta.coverUrl` | string | URL del thumbnail (CDN, expira) |
| `videoMeta.duration` | number | duración en segundos |
| `videoMeta.height/width` | number | dimensiones |
| `videoMeta.format` | string | "mp4" usual |
| `isAd` | bool | filtrar ads para no contaminar engagement orgánico |
| `isPinned` | bool | marcar pinned (suelen tener engagement inflado) |
| `isSlideshow` | bool | tipo alternativo |
| `isSponsored` | bool | filtrar como ads |
| `authorMeta` | object | ver sección abajo (embedido en cada item) |

### Engagement formula

```
engagement = diggCount + commentCount + shareCount
```

`playCount` (views) **NO** se cuenta como engagement — se reporta aparte como métrica de alcance.

### Tipo canónico

| Condición | `tipo` canónico |
|---|---|
| `isSlideshow: true` | "Slideshow" |
| default | "Video" |

### Campos del perfil embebidos en `authorMeta`

`authorMeta` viene **idéntico** en todos los items del run (es el mismo perfil). El extractor toma `items[0].authorMeta` para construir `accounts.TikTok`.

| Campo `authorMeta.*` | Uso en Supabase |
|---|---|
| `name` | `username` (e.g. "comapanco") |
| `nickName` | `display_name` |
| `id` | id de usuario TT |
| `signature` | `bio` |
| `fans` | `followers` |
| `following` | `following_n` |
| `friends` | (no persistido) |
| `heart` | likes acumulados de TODOS los videos históricos (no del periodo) |
| `video` | `posts_total` (total de videos en el perfil) |
| `verified` | `verified` bool |
| `ttSeller` | (no persistido) |
| `privateAccount` | (no persistido) |
| `commerceUserInfo.commerceUser` | `is_business` |
| `commerceUserInfo.category` | `category` |
| `avatar` | URL del avatar (efímera, no persistida) |

### Ejemplo real de item (recorte, campos clave)

```json
{
  "id": "7662869627386580225",
  "webVideoUrl": "https://www.tiktok.com/@comapanco/video/7662869627386580225",
  "text": "¿Sin Comapan? ¡ESO SÍ JAMASSS! 😂 #fyp #productos #snacks #oficina",
  "createTimeISO": "2026-07-15T21:29:07.000Z",
  "diggCount": 10,
  "commentCount": 1,
  "shareCount": 0,
  "playCount": 627,
  "hashtags": [
    {"id": "...", "name": "fyp", ...},
    {"id": "...", "name": "productos", ...}
  ],
  "videoMeta": {
    "coverUrl": "https://p16-sign.tiktokcdn-us.com/...",
    "duration": 13,
    "height": 1024,
    "width": 576,
    "format": "mp4"
  },
  "isAd": false,
  "isPinned": false,
  "isSlideshow": false,
  "authorMeta": {
    "name": "comapanco",
    "nickName": "Comapan",
    "fans": 15000,
    "following": 42,
    "video": 87,
    "verified": true,
    "signature": "..."
  }
}
```

## Deprecated — `clockworks/tiktok-scraper` (NO USAR)

- **ID:** `GdWCkxBtKWOsKjdch`
- **Status:** ❌ **descartado el 2026-07-21**

### Motivo del descarte

Devolvía dataset stale de forma intermitente: aunque el actor reportaba "Succeeded", los items retornados no incluían los posts publicados en los últimos días. La causa raíz probable es caché interno del actor en la primera fase de scraping (search de perfil).

Casos documentados:
- 2026-07-16: 0 posts retornados del run pese a haber 3 posts nuevos en el perfil.
- 2026-07-21: 3 posts retornados pese a haber 5 posts nuevos en el perfil.

Ambos casos se validaron corriendo el `tiktok-profile-scraper` inmediatamente después con el mismo input — ese sí retornaba todos los posts frescos.

### Migración

En `ingest_monthly.py` la llamada al `posts-scraper` fue eliminada por completo. En `config/clients/comapan.yaml` el bloque `tiktok.apify.posts` puede quedar como referencia histórica pero no se lee.

### Si vuelve a ser necesario probarlo

- Correrlo manualmente desde el Apify Console, no desde nuestro pipeline.
- Comparar output contra `tiktok-profile-scraper` con el mismo input.
- Solo reactivarlo si Apify publica una nota confirmando que el problema de cache está resuelto.
