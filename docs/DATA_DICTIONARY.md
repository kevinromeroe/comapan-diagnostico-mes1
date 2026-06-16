# Data Dictionary — Shape Canónico `DATA`

Este documento define **el contrato de datos** que el pipeline produce y que el `template.html` consume. Es el shape canónico v1.0.0.

Cualquier cambio incompatible con este shape requiere subir la versión `data_shape_version` en `config/global.yaml` y migrar el renderer.

---

## Estructura de alto nivel

```js
const DATA = {
  generated_at: "DD/MM/YYYY",        // fecha de generación en formato display
  ventana: { desde: "YYYY-MM-DD", hasta: "YYYY-MM-DD" },
  accounts: { Instagram: {...}, Facebook: {...}, TikTok: {...}, LinkedIn: {...} },
  consolidated: [ {plataforma, ...}, ... ],   // una fila por plataforma
  instagram: { ...shape de plataforma... },
  facebook:  { ...shape de plataforma... },
  tiktok:    { ...shape de plataforma... },
  linkedin:  { ...shape de plataforma... },
  fb_undated: <number>,              // posts FB sin fecha (caveat del scraper)
  fb_total: <number>,                // total FB incluyendo undated
  snapshots_history: [ {snapshot_date, plataforma, metrica, valor, fuente}, ... ]
};
```

---

## `accounts[plataforma]`

Snapshot del perfil al momento del run. Todos los campos son strings (incluso números).

| Campo | Tipo | Notas |
|---|---|---|
| bio | string | Biografía / descripción |
| business_account | string ("True"/"False") | — |
| categoria | string | Categoría de negocio |
| direccion | string | Dirección física |
| nombre | string | Nombre mostrado |
| page_likes | string | Solo Facebook |
| plataforma | string | "Instagram", "Facebook", etc. |
| posts_totales | string | Total histórico de posts (no de la ventana) |
| rating | string | Solo Facebook |
| seguidores | string | Seguidores totales |
| siguiendo | string | A cuántos sigue |
| snapshot_fecha | string YYYY-MM-DD | Fecha del snapshot |
| telefono | string | — |
| url_externa | string | Link del bio |
| username | string | Handle (sin @) |
| verified | string ("True"/"False") | — |
| views_totales_90d | string | Solo TikTok |
| website | string | — |

---

## `consolidated[]`

Una fila por plataforma. Sirve para la tabla "Las cuatro cuentas en una sola tabla" del reporte.

| Campo | Tipo | Descripción |
|---|---|---|
| plataforma | string | Nombre |
| username | string | Handle |
| seguidores | string | Vacío si no aplica |
| posts_90d | string | Posts en la ventana |
| engagement_total_90d | string | Suma de engagement |
| engagement_promedio_post | string | Promedio por post |
| top_post_url | string | URL al mejor post |
| top_post_engagement | string | Engagement del top |
| snapshot_fecha | string | YYYY-MM-DD |

---

## `<plataforma>` (shape canónico por plataforma)

Estructura idéntica para `instagram`, `facebook`, `tiktok`, `linkedin`:

```python
{
  "n_posts": <int>,
  "engagement_total": <int>,
  "engagement_promedio": <float>,
  "engagement_mediana": <int>,
  "by_type": {
    "labels": [str, ...],                    # ej ["Image", "Sidecar", "Video"]
    "counts": [int, ...],                    # cuántos posts por tipo
    "engagement": [int, ...],                # engagement total por tipo
    "engagement_promedio": [float, ...],     # engagement promedio por tipo
  },
  "by_day": {
    "labels": ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"],
    "counts": [int, ...],
    "engagement_promedio": [float, ...],
  },
  "by_hour": {
    "labels": [str, ...],                    # horas con posts ("8","9","10",...)
    "counts": [int, ...],
  },
  "by_week": {
    "labels": [str, ...],                    # ["2026-S06","2026-S07",...]
    "counts": [int, ...],
    "engagement": [int, ...],
  },
  "top_hashtags": [                          # top 10
    [str, int],                              # [tag, n_apariciones]
    ...
  ],
  "captions_avg_len": <float>,
  "top5": [
    {
      "fecha": "YYYY-MM-DD",
      "tipo": str,                           # "Video", "Image", "post", etc.
      "url": str,                            # URL del post
      "media_url": str,                      # ruta local: assets/thumbs/<prefix>-<hash>.jpg
      "caption": str,                        # truncado a 150 chars
      "engagement": int,
      "likes": int,
      "comentarios": int,
    },
    ...                                       # 5 elementos
  ],
}
```

---

## Reglas de cálculo

### Engagement por plataforma

| Plataforma | Fórmula |
|---|---|
| Instagram | `likesCount + commentsCount` |
| Facebook | `reactions + comments + shares` |
| TikTok | `diggCount + commentCount + shareCount` |
| LinkedIn | `reactions + comments + shares` |

### Engagement rate (cuando aplica)

```
engagement_rate = (engagement_total / impresiones_o_alcance) × 100
```

Solo se calcula si la plataforma expone impresiones/alcance. En este momento ninguna de las 4 lo expone vía scraping; queda como punto ciego documentado.

### Top 5 posts

Ordenados por `engagement` desc. Empates se desempatan por `likes` desc, luego `fecha` desc.

### Top hashtags

Conteo de apariciones únicas por hashtag. Ordenados desc, top 10. Case-insensitive en el conteo pero se preserva el case del primer uso para mostrar.

### Mediana

Mediana de engagement de los posts de la ventana. Útil para identificar outliers contra el promedio.

---

## Cuándo subir la versión del schema

| Cambio | Versión |
|---|---|
| Agregar campo opcional al final | minor (1.0.0 → 1.1.0) |
| Renombrar campo | major (1.0.0 → 2.0.0) |
| Cambiar tipo de un campo | major |
| Cambiar fórmula de cálculo de un valor | minor con nota visible |
| Agregar nueva plataforma | minor |

Cualquier cambio major requiere también refactor del `template.html` y bump correspondiente.
