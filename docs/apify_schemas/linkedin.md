# Apify Schema · LinkedIn (`harvestapi/linkedin-company-posts`)

Mapeo del actor `harvestapi/linkedin-company-posts` (Act ID `WI0tj4Ieb5Kq458gB`). Dataset de referencia: `Kdxcm91vqnLxpgKmM`.

Un objeto por publicación. El perfil de la empresa va embebido en `author` de cada item.

## Campos relevantes a nivel post

| Campo | Tipo | Uso |
|---|---|---|
| `id` | string | join key |
| `type` | string | "post" (por ahora siempre, mantener por compatibilidad) |
| `linkedinUrl` | string | `top5.url` |
| `shareUrn` | string | id formato URN |
| `entityId` | string | id de actividad |
| `content` | string | caption — captions_avg_len + hashtags |
| `contentAttributes` | array | mentions, hashtags estructurados (cuando aparece) |
| `postedAt.timestamp` | number | unix ms |
| `postedAt.date` | string ISO 8601 | `by_day`, `by_week`, `by_hour` |
| `postedAt.postedAgoShort` | string | "4d", "2w" — display |
| `postImages[]` | array | URLs de imágenes adjuntas |
| `postVideo.thumbnailUrl` | string | thumbnail si es video |
| `postVideo.videoUrl` | string | URL del video |
| `engagement.likes` | number | likes (`numLikes`) |
| `engagement.comments` | number | comentarios |
| `engagement.shares` | number | shares |
| `engagement.reactions[]` | array<object> | desglose por tipo de reacción |
| `engagement.reactions[].type` | string | "LIKE", "PRAISE", "EMPATHY", etc. |
| `engagement.reactions[].count` | number | conteo por tipo |
| `socialContent.shareUrl` | string | URL canónica del share |
| `query.targetUrl` | string | URL del input (trazabilidad) |

## Engagement formula

```
engagement = likes + comments + shares
```

(Si `shares` no aparece, default 0.)

## Tipo de publicación canónico

LinkedIn marca todo como "post". Mapeo basado en contenido:

| Condición | `tipo` canónico |
|---|---|
| `postVideo` presente | "Video" |
| `postImages` array no vacío | "Image" |
| solo texto | "Text" |
| (default) | "post" |

## Campos del perfil de empresa embebidos en `author`

| Campo `author.*` | Uso |
|---|---|
| `name` | nombre de la empresa → `accounts.LinkedIn.nombre` |
| `universalName` | handle → `accounts.LinkedIn.username` |
| `type` | "company" esperado |
| `id` | id numérico de LinkedIn |
| `urn` | URN |
| `linkedinUrl` | URL al perfil |
| `info` | string con seguidores en texto natural, e.g. "5,020 followers" → parsear a `accounts.LinkedIn.seguidores` |
| `avatar.url` | URL del logo (efímera) |
| `website` | URL externa |

### Parseo de seguidores

El campo `author.info` viene como string: `"5,020 followers"`. El extractor debe:

```python
import re
m = re.match(r"([\d,]+)\s+followers", info or "")
followers = int(m.group(1).replace(",", "")) if m else None
```

Si el formato cambia, fallback a `None` y log warning.

## Caveats

- **`postedAt.timestamp` viene en milisegundos**, no segundos (a diferencia de TikTok/FB). Dividir entre 1000 si se va a comparar con unix.
- El campo `query.sessionId` cambia entre runs — útil para debug pero no se persiste.
- LinkedIn devuelve **menos posts** por scrape (la página de empresa muestra menos histórico). Para Comapan con 16 posts en 90 días, el actor cubre cómodo. Para cuentas más activas verificar resultsLimit.
- **Reacciones detalladas**: `engagement.reactions[]` permite analizar qué emoción predomina (LIKE = aprobación, PRAISE = admiración, EMPATHY = conexión emocional, MAYBE_INTEREST, INTEREST). No se usa hoy pero queda mapeado para hallazgos futuros.

## Costos

- $2.00 USD por 1.000 posts
- Para Comapan con ~5 posts quincenales: ~$0.01 USD/run

Es el actor más barato del set.
