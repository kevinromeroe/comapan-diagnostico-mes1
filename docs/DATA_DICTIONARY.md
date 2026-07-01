# DATA DICTIONARY — Comapan

## Esquema Supabase

Proyecto: `pmeotakzlgkjdbwdttyf`

### Tabla `clients`
Cliente que paga por el servicio.

| Columna | Tipo | Notas |
|---|---|---|
| id | text (PK) | Ej. `comapan` |
| name | text | "Comapan" |
| agency_name | text | "Catorce Días Colombia S.A.S." |

### Tabla `periods`
Periodos de análisis (baseline + meses).

| Columna | Tipo | Notas |
|---|---|---|
| id | text (PK) | `diagnostico`, `2026-06`, `2026-07`, ... |
| client_id | text (FK → clients.id) | |
| label | text | "Diagnóstico (Ene-May 2026)", "Junio 2026" |
| starts_on | date | Primer día del periodo |
| ends_on | date | Último día del periodo |
| is_baseline | boolean | true para `diagnostico`, false para meses |

### Tabla `accounts`
Snapshot del perfil de cada red por periodo.

| Columna | Tipo | Notas |
|---|---|---|
| client_id | text | |
| period_id | text (FK → periods.id) | |
| platform | text | `instagram`, `facebook`, `tiktok`, `linkedin` |
| username | text | Handle sin @ |
| display_name | text | Nombre mostrado |
| followers | int | IG, TT, LI |
| page_likes | int | FB solamente |
| posts_total | int | Total histórico (no del periodo) |
| verified | boolean | |
| is_business | boolean | |
| snapshot_at | timestamp | Momento del scrape |
| raw | jsonb | Response crudo del actor |

**PK compuesta:** (client_id, period_id, platform)

### Tabla `posts`
Publicaciones individuales.

| Columna | Tipo | Notas |
|---|---|---|
| id | text (PK) | ID nativo de la red (IG post id, FB postId, etc.) |
| client_id | text | |
| platform | text | |
| url | text | URL pública del post |
| type | text | "Image", "Video", "Sidecar", "Photo", "Text", "post" |
| caption | text | Texto original |
| hashtags | text[] | |
| posted_at | timestamptz | UTC |
| likes | int | |
| comments | int | |
| shares | int | |
| engagement | int | likes + comments + shares |
| media_url | text | URL CDN del thumbnail (expira) |
| **media_url_local** | text | `/assets/thumbs/xxx.jpg` (persistido en el repo) |
| **thumbnail_downloaded_at** | timestamptz | Cuando se descargó localmente |
| **tags** | jsonb | Ej. `["producto", "receta"]` (primary + secondary) |
| **tag_primary** | text | Ej. `producto` |
| **tagged_at** | timestamptz | Cuando Gemini clasificó |
| is_ad | boolean | |
| is_pinned | boolean | |
| raw | jsonb | Response crudo |

**NOTA:** posts NO tiene `period_id`. Se asigna a un periodo vía filtro por `posted_at`.

### Tabla `aggregates`
Métricas pre-calculadas por (periodo, plataforma).

| Columna | Tipo | Notas |
|---|---|---|
| client_id | text | |
| period_id | text | |
| platform | text | |
| metric_name | text | `by_type`, `by_day`, `by_hour`, `by_week`, `engagement_stats`, `top_hashtags`, `top5`, etc. |
| metric_value | jsonb | Contenido depende del metric_name |

### Tabla `summaries`
Narrativas LLM por periodo.

| Columna | Tipo | Notas |
|---|---|---|
| client_id | text | |
| period_id | text | |
| resumen | text | Texto ejecutivo generado por Gemini (opcional) |
| headlines | jsonb | Por plataforma |
| chart_insights | jsonb | Por chart_id |
| generated_by | text | Modelo usado |
| generated_at | timestamptz | |

**NOTA:** En la implementación actual, el resumen ejecutivo se computa en el build script directamente desde los datos, no de esta tabla. La tabla se mantiene por compatibilidad.

---

## Shape del `DATA` embebido en el HTML

Cada `index.html` de periodo tiene un `const DATA = {...}` con:

```js
{
  generated_at: "DD/MM/YYYY",
  ventana: { desde: "YYYY-MM-DD", hasta: "YYYY-MM-DD" },
  accounts: { Instagram: {...}, Facebook: {...}, TikTok: {...}, LinkedIn: {...} },
  consolidated: [ {plataforma, ...}, ... ],
  instagram: { <shape de plataforma> },
  facebook:  { <shape de plataforma> },
  tiktok:    { <shape de plataforma> },
  linkedin:  { <shape de plataforma> },
  category_analysis: { mix_global, performance, by_platform, by_type, gaps },
  deltas: { global, instagram, facebook, tiktok, linkedin } | null,  // null en diagnostico
  periodo_label: "Junio 2026",
  periodo_id: "2026-06",
  ...
}
```

### Shape por plataforma

```js
{
  n_posts: <int>,
  engagement_total: <int>,
  engagement_promedio: <float>,
  engagement_mediana: <int>,

  // Agregaciones SOLO con posts típicos (excluyen atípicos):
  by_type:  { labels, counts, engagement, engagement_promedio },
  by_day:   { labels: DOW, counts, engagement_promedio },
  by_hour:  { labels, counts, engagement_promedio, _timezone: "America/Bogota" },
  by_week:  { labels: ISO weeks, counts, engagement },
  by_day_hour: { matrix: 7×24, labels_dow, labels_hour, counts },
  top_hashtags: [[tag, n], ...],
  captions_avg_len: <float>,

  // Posts individuales:
  top5:     [ {url, tipo, fecha, likes, caption, media_url, engagement, comentarios, tags, tag_primary}, ... ],
  atipicos: [ ... ],  // engagement > 5x mediana
  worst5:   [ ... ],  // solo si n_posts > 5

  outlier_threshold: <float>,
  outlier_rule: "engagement > 5x mediana del periodo",

  // Análisis de tags:
  tag_summary:    { producto: 5, receta: 3, ... },
  tag_engagement: { producto: 89.2, receta: 145.6, ... },
}
```

### Shape de deltas MoM

```js
deltas: {
  global: {
    total_posts_pct:         <float | null>,
    total_engagement_pct:    <float | null>,
    engagement_por_post_pct: <float | null>,
  },
  instagram: {
    n_posts_pct:              <float | null>,
    engagement_total_pct:     <float | null>,
    engagement_promedio_pct:  <float | null>,
    engagement_mediana_pct:   <float | null>,
  },
  facebook: { ... },
  tiktok:   { ... },
  linkedin: { ... },
}
```

`null` en un campo indica que no había data en el mes previo (imposible calcular el porcentaje).
`deltas === null` en la raíz indica que el periodo es el baseline (diagnostico).
