# Apify Schemas · TikTok

Dos actores de `clockworks`: el de perfil y el de posts. El de posts ya incluye perfil embebido en `authorMeta`, así que para esta cuenta **uno solo basta**.

---

## `clockworks/tiktok-scraper` (Act ID `GdWCkxBtKWOsKjdch`)

El "todo en uno" — devuelve un objeto por video con `authorMeta` embebido (datos del perfil). Dataset de referencia: `Ry8L7eAfQbFbl8yO8`.

### Campos relevantes a nivel video

| Campo | Tipo | Uso |
|---|---|---|
| `id` | string | join key |
| `webVideoUrl` | string | `top5.url` |
| `text` | string | caption — captions_avg_len + hashtags |
| `textLanguage` | string | filtro de calidad ("es" esperado) |
| `createTime` | number (unix) | redundante |
| `createTimeISO` | string ISO 8601 | `by_day`, `by_week`, `by_hour` |
| `diggCount` | number | likes |
| `commentCount` | number | comentarios |
| `shareCount` | number | shares |
| `playCount` | number | visualizaciones (views) |
| `collectCount` | number | guardados (saves) |
| `repostCount` | number | reposts |
| `hashtags` | array<object> | `[{id, name, title, cover}]` → tomar `name` |
| `videoMeta.coverUrl` | string | URL del thumbnail |
| `videoMeta.duration` | number | duración en segundos |
| `videoMeta.height/width` | number | dimensiones |
| `videoMeta.format` | string | "mp4" usual |
| `isAd` | bool | filtrar ads para no contaminar engagement orgánico |
| `isPinned` | bool | marcar pinned (suelen tener engagement inflado) |
| `isSlideshow` | bool | tipo alternativo |
| `isSponsored` | bool | filtrar como ads |
| `fromProfileSection` | string | "videos", "reposted", etc. |
| `input` | string | username del input (trazabilidad) |

### Engagement formula

```
engagement = diggCount + commentCount + shareCount
```

`playCount` (views) NO se cuenta como engagement — se reporta aparte como métrica de alcance.

### Tipo canónico

TikTok es siempre Video salvo cuando `isSlideshow: true`. Mapeo:

| Condición | `tipo` canónico |
|---|---|
| `isSlideshow: true` | "Slideshow" |
| default | "Video" |

---

## Campos del perfil embebidos en `authorMeta`

| Campo `authorMeta.*` | Uso |
|---|---|
| `name` | username (e.g. "comapanco") |
| `nickName` | nombre mostrado |
| `id` | id de usuario |
| `signature` | bio |
| `fans` | seguidores → `accounts.TikTok.seguidores` |
| `following` | a cuántos sigue → `accounts.TikTok.siguiendo` |
| `friends` | amigos |
| `heart` | likes acumulados de TODOS los videos (no del periodo) |
| `video` | total de videos en el perfil → `accounts.TikTok.posts_totales` |
| `digg` | videos likeados por el usuario |
| `verified` | bool |
| `ttSeller` | bool — vendedor TikTok |
| `privateAccount` | bool |
| `commerceUserInfo.commerceUser` | bool |
| `commerceUserInfo.category` | string |
| `avatar` | URL del avatar (efímera) |

Como `authorMeta` es **idéntico** en todos los items del run, el extractor toma `items[0].authorMeta` para construir `accounts.TikTok`.

---

## `clockworks/tiktok-profile-scraper` (Act ID `0FXVyOXXEmdGcV88a`)

Mismo shape que el "todo en uno". Se invocó en el Mes 1 pero es **redundante** dado que `tiktok-scraper` ya trae perfil. **Recomendación**: desactivar este actor en el schedule para ahorrar créditos. Si por alguna razón llegamos a necesitar solo el perfil (sin scrapear videos), reactivar.

Dataset de referencia: `XZj59PJHKrIFfLfSh` (mismo shape de campos).
