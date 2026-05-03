# Diagnóstico Comapan — Mes 1

Servicio mensual de analítica de redes sociales para **Catorce Días Colombia** sobre la cuenta **Comapan**.
Generado por **Datalítica Colombia S.A.S.**

Entrega del Mes 1: diagnóstico ejecutivo del estado actual de las cuentas digitales (últimos 90 días) sobre Instagram, Facebook, TikTok y LinkedIn.

---

## Convenciones del servicio

### Convención "Learn" en visualizaciones
**Regla:** toda gráfica del dashboard (y de cualquier entregable visual del servicio) debe ir acompañada de una lectura interpretativa breve (1-2 líneas) calculada a partir de los datos de esa gráfica específica.

**Por qué:** El cliente paga por el insight, no por el gráfico. Una visualización sin lectura interpretativa explícita queda en "data bonita" y diluye el valor del servicio.

**Cómo se aplica:**
- Cada gráfica en `dashboard.html` lleva un bloque de lectura debajo del canvas.
- El texto se deriva dinámicamente de los datos reales (calculado en JS), no es genérico.
- Aplica a TODOS los entregables visuales: dashboards HTML, decks, reportes PDF.
- Si una gráfica no permite extraer un Learn claro, se replantea si vale la pena la gráfica.

### Lenguaje publicista
Todos los entregables visuales se escriben en lenguaje accesible al equipo de marketing y publicidad — sin jerga técnica.
- **No se usa:** "engagement promedio", "Image", "Sidecar", "taxonomía de hashtags", "delta", "discovery orgánico"
- **Sí se usa:** "interacciones", "Foto", "Carrusel", "Reel", "etiquetas fijas", "más alcance"

---

## Arquitectura

```
[Apify Actors] → JSON crudo → process.py → CSVs limpios → build_dashboard.py → dashboard.html
                                              ↓
                                       snapshots_history.csv  (serie histórica acumulativa)
```

- **Extracción:** Apify (un actor por red, corridas one-shot por ahora).
- **Procesamiento:** Python 3 (`process.py`).
- **Almacenamiento:** CSVs locales (un archivo por red + consolidado + snapshot histórico).
- **Visualización:** página web autocontenida (`dashboard.html`) — Chart.js desde CDN, imágenes locales en `assets/thumbs/`.
- **Entregable narrativo:** Google Doc con diagnóstico, hallazgos y recomendaciones (próxima fase).

Sin GitHub Actions, sin cron, sin servicio recurrente — todo eso queda para el Mes 2 una vez Catorce Días valide el MVP.

---

## Pipeline operativo

### Para regenerar todo desde cero
```bash
python3 process.py        # procesa los JSON, genera CSVs, descarga thumbnails
python3 build_dashboard.py # regenera dashboard.html
open dashboard.html
```

### Pasos del `process.py`
1. Lee los datasets crudos de Apify del directorio (con patrón `dataset_<actor>_*.json`).
2. Filtra cada plataforma a la ventana de 90 días.
3. Calcula columnas derivadas: `dia_semana`, `hora` (TZ Bogotá), `engagement_total`, `engagement_rate`, `longitud_caption`, `hashtags`.
4. Para los **top 5 posts por engagement** de cada red, descarga la imagen miniatura localmente a `assets/thumbs/` (la URL del CSV se reemplaza por la ruta local — el dashboard queda 100% portátil).
5. Para TikTok específicamente, las thumbnails se obtienen vía el endpoint público `tiktok.com/oembed` (el actor de Apify no las entrega).
6. Apende un snapshot del día a `snapshots_history.csv` (idempotente: no duplica si ya hay registro de hoy).

### Pasos del `build_dashboard.py`
1. Lee los CSVs.
2. Calcula agregados por plataforma: by_type, by_day, by_hour, by_week, top_hashtags.
3. Embebe todo como JSON inline en el HTML.
4. Renderiza el dashboard estático (no requiere servidor).

---

## Apify — actors usados

| Red | Actor | Propósito | Costo aprox. |
|---|---|---|---|
| Instagram | `apify/instagram-scraper` | Posts + cuenta + hashtags | <$0.20 |
| Facebook (posts) | `apify/facebook-posts-scraper` | Posts del feed | ~$1 |
| Facebook (página) | `apify/facebook-pages-scraper` | Followers/likes de página + info | ~$0.01 |
| TikTok | `clockworks/tiktok-profile-scraper` | Videos + métricas | ~$0.07 |
| LinkedIn | `harvestapi/linkedin-company-posts` | Posts de página corporativa | ~$2-3 |

**Costo total aproximado por corrida completa:** $3-5 USD.

### Inputs JSON usados (referencia para futuras corridas)

#### Instagram
```json
{
  "directUrls": ["https://www.instagram.com/comapan_co/"],
  "resultsType": "posts",
  "resultsLimit": 200,
  "onlyPostsNewerThan": "2026-02-03",
  "addParentData": true
}
```

#### Facebook posts
```json
{
  "startUrls": [{"url": "https://www.facebook.com/ComapanCo/"}],
  "resultsLimit": 200,
  "onlyPostsNewerThan": "2026-02-03"
}
```

#### Facebook page
```json
{
  "startUrls": [{"url": "https://www.facebook.com/ComapanCo/"}]
}
```

#### TikTok
```json
{
  "profiles": ["comapanco"],
  "shouldDownloadCovers": false,
  "shouldDownloadAvatars": false,
  "shouldDownloadVideos": false,
  "shouldDownloadSlideshowImages": false
}
```
Nota: `shouldDownloadCovers: true` no agrega URLs al output. Las thumbnails se obtienen vía `tiktok.com/oembed` en el procesamiento.

#### LinkedIn
```json
{
  "targetUrls": ["https://www.linkedin.com/company/comapan-s-a-/"],
  "maxPosts": 100,
  "includeQuotePosts": true,
  "includeReposts": true
}
```

---

## Limitaciones conocidas y decisiones tomadas

### Facebook — 13 posts sin fecha (de 42)
- **Causa:** el actor `apify/facebook-posts-scraper` no devuelve `publish_time` para algunos formatos (principalmente fotos individuales y álbumes). Solo lo devuelve consistentemente para reels y videos.
- **Vías exploradas y descartadas:**
  - Re-correr con otro actor: incierto y costoso (~$1 sin garantía).
  - Scrapear el HTML de cada URL: el HTML público de Facebook no expone el timestamp en formato extraíble (solo aparecen timestamps de "ahora" cuando se sirve la página).
  - Derivar fecha del ID numérico del post: los IDs antiguos sí codifican timestamp pero los nuevos `pfbid...` no.
- **Decisión:** los 13 posts sin fecha se incluyen en KPIs absolutos (engagement total, top 5) pero quedan fuera del análisis temporal (cadencia semanal, día de la semana). El dashboard ya maneja este caso silenciosamente.

### TikTok — sin conteo de seguidores
- **Causa:** ni `clockworks/tiktok-scraper` ni `clockworks/tiktok-profile-scraper` entregan el campo `fans` en el dataset, contrario a lo que indica la documentación oficial.
- **Decisión:** el dashboard usa **views totales (90d)** como métrica de alcance para TikTok. Cuando se obtenga el dato de SocialBlade (capa manual pendiente), se incorpora.

### Histórico de seguidores (las 4 redes)
- **Causa:** ningún proveedor gratuito ofrece histórico retroactivo de seguidores para Comapan en estas 4 redes (Wayback Machine prácticamente no tiene snapshots; SocialBlade tiene IG y TikTok pero está protegido por Cloudflare).
- **Decisión adoptada:** se construye una serie histórica desde HOY mediante `snapshots_history.csv` que apende un registro cada vez que se corre `process.py`. En 4 semanas se tendrá serie real para Catorce Días.

---

## Alcance entregable del diagnóstico

### Lo que SÍ se entrega (data 100% pública)
| Bloque | Métricas |
|---|---|
| Audiencia digital actual | Seguidores IG/LinkedIn, page likes FB, views totales TikTok |
| Volumen | Posts publicados, cadencia semanal, gaps |
| Mix de contenido | % por formato (Foto, Carrusel, Reel) |
| Performance pública | Likes, comentarios, shares, views |
| Engagement por post | Promedio y mediana |
| Top 5 publicaciones | Por engagement, con miniatura visible |
| Patrones temporales | Día de la semana y hora con mejor desempeño |
| Análisis de copy | Longitud de captions, hashtags usados |
| Evolución semanal | Engagement por red, semana a semana |

### La siguiente capa (apertura para Mes 2+)
Métricas privadas que se desbloquean cuando se conectan los accesos analíticos:
- Alcance e impresiones por publicación
- Guardados, compartidos privados, demografía
- Stories y métricas de stories
- Tráfico web a comapan.com.co (GA4)

Esta sección se presenta al cliente en clave constructiva ("la siguiente capa de análisis"), no como queja por falta de acceso.

---

## Huecos opcionales para evaluar después del MVP

Tres extensiones que se decidirán **después** de revisar el MVP con datos reales. No están incluidas en el alcance base.

### Hueco 1 — Comentarios completos de los top posts (~$1 USD)
Sección de "voz del consumidor". Actor `apify/instagram-comment-scraper`.

### Hueco 2 — Highlights de Instagram (~$0.50 USD)
Análisis de la vitrina permanente. Actor `apify/instagram-scraper` con `resultsType: "details"`.

### Hueco 3 — Posts donde etiquetan a @comapan_co (~$1-2 USD)
Termómetro de brand love (UGC).

---

## Estructura de archivos

```
Cuesto/
├── README.md                                  # este archivo
├── process.py                                 # extracción + transformación
├── build_dashboard.py                         # generador del HTML
├── dashboard.html                             # entregable visual (autocontenido)
│
├── dataset_instagram-scraper_*.json           # raw IG
├── dataset_facebook-posts-scraper_*.json      # raw FB posts
├── dataset_facebook-pages-scraper_*.json      # raw FB página
├── dataset_tiktok-profile-scraper_*.json      # raw TikTok
├── dataset_linkedin-company-posts_*.json      # raw LinkedIn
│
├── instagram_posts.csv                        # IG procesado
├── facebook_posts.csv                         # FB procesado
├── tiktok_posts.csv                           # TT procesado
├── linkedin_posts.csv                         # LI procesado
├── consolidated.csv                           # vista resumen por red
├── accounts_snapshot.csv                      # snapshot de cuenta hoy
├── snapshots_history.csv                      # serie temporal acumulativa (idempotente)
│
└── assets/
    ├── logo-comapan.svg / .png                # logo del cliente analizado
    ├── logo-14dias.svg                        # logo de la agencia (cliente directo)
    ├── panchi.webp                            # mascota Comapan
    └── thumbs/                                # miniaturas locales de los top 5 por red
```

---

## Estado actual

- [x] 4 redes extraídas vía Apify (IG, FB posts + página, TikTok, LinkedIn)
- [x] Pipeline `process.py` + `build_dashboard.py` operativo
- [x] Dashboard ejecutivo con identidad de marca Comapan + Catorce Días + Datalítica
- [x] Convención "Learn" implementada y documentada
- [x] Lenguaje publicista aplicado en hallazgos y recomendaciones
- [x] Thumbnails reales descargadas localmente (4 redes)
- [x] Serie histórica iniciada (`snapshots_history.csv`)
- [ ] Datos de SocialBlade (IG y TikTok) — pendiente carga manual
- [ ] Google Doc del diagnóstico narrativo (3-5 páginas)
- [ ] MVP review con Catorce Días
- [ ] Decisión sobre los 3 huecos opcionales
