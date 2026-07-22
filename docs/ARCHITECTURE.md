# ARQUITECTURA — Reporte Comapan

## Diagrama de flujo

```
                    ┌────────────────────────┐
                    │      Apify (SaaS)      │
                    │   5 actores            │
                    │   (IG/FB pages/FB posts│
                    │      TT profile/LI)    │
                    └──────────┬─────────────┘
                               │ ingest_monthly.yml
                               │ (manual, workflow_dispatch)
                               ▼
                    ┌────────────────────────┐
                    │   Supabase Postgres    │
                    │   project pmeotakzl…   │
                    │  ┌──────────────────┐  │
                    │  │ posts, accounts, │  │
                    │  │ aggregates, ...  │  │
                    │  └──────────────────┘  │
                    └──────────┬─────────────┘
                               │
                               │ build_diagnostico_
                               │   extendido.yml
                               │ (manual)
                               ▼
                    ┌────────────────────────┐
                    │  Gemini 2.5 Flash      │
                    │  (categorización 12    │
                    │   tags)                │
                    └──────────┬─────────────┘
                               │
                               ▼
                    ┌────────────────────────┐
                    │  GitHub repo main      │
                    │  /  (landing)          │
                    │  /diagnostico/         │
                    │  /2026-06/, /2026-07/  │
                    │  /assets/thumbs/*.jpg  │
                    └──────────┬─────────────┘
                               │
                               │ GitHub Pages deploy
                               ▼
                    ┌────────────────────────┐
                    │ comapan.datalitica.    │
                    │      com.co            │
                    └────────────────────────┘
```

## Componentes clave

### Pipeline de scraping (`scripts/ingest_monthly.py`)

- Corre 5 actores de Apify secuencialmente con caps de seguridad por actor.
- Filtra posts al calendario mensual en zona Bogotá (UTC-5).
- Persiste accounts, posts y aggregates en Supabase.
- **Descarga thumbnails inmediatamente** post-scrape (URLs CDN expiran en horas).
- Comprime a 400px width JPEG q60, guarda en `/assets/thumbs/` con path absoluto.
- Actualiza `posts.media_url_local` vía PATCH REST.
- Commitea los thumbnails al repo antes de terminar.

**Nota importante sobre TikTok (fix 2026-07-21):** solo se corre el actor `clockworks/tiktok-profile-scraper` (ID `0FXVyOXXEmdGcV88a`). Ese actor retorna cuenta + posts frescos en un mismo dataset. Se descartó `clockworks/tiktok-scraper` (ID `GdWCkxBtKWOsKjdch`) porque devolvía dataset stale de forma intermitente.

### Pipeline de build (`scripts/build_diagnostico_extendido_html.py`)

Genera el HTML final. Modo por defecto: `--period all` (regenera todos los periodos existentes en la tabla `periods`).

Por cada periodo:

1. Lee accounts, aggregates y posts de Supabase (`sb.select("posts", filter=f"client_id=eq.{CLIENT_ID}")`).
2. **Filtra posts al período** con `VENTANA_DESDE` y `VENTANA_HASTA` (Bogotá). Este filtro se agregó en el fix del heatmap 2026-07-16.
3. Split posts en atípicos (`engagement > 5× mediana`) y típicos.
4. Calcula aggregates de gráficas usando solo típicos.
5. Genera heatmap día×hora en zona Bogotá, sólo con posts del período.
6. Tagea posts sin `tag_primary` con Gemini (12 categorías fijas). Persiste tags a Supabase.
7. Fallback keyword-based si Gemini falla (evita "marca" masivo).
8. Propaga tags a top5/atípicos/worst5 (que son copias, no refs).
9. Calcula `category_analysis` (mix, performance, heatmaps, gaps).
10. Calcula deltas MoM vs mes anterior (solo si aplica; `null` en baseline).
11. Genera resumen ejecutivo dinámico basado en la data del periodo.
12. Reemplaza `const DATA = {...}` y `const REPORT_META = {...}` en el template.
13. Escribe a `/{period}/index.html`. Diagnóstico también sobreescribe `/index.html` (landing).

### Templates

Solo hay 2 archivos vivos:

- `diagnostico/index.html` — template fuente, se auto-sobreescribe en cada build.
- `index.html` — landing (copia del diagnóstico).
- `/2026-MM/index.html` — clonado del diagnóstico + DATA reemplazado.

Todo estilo, CSS, JS reutilizable vive dentro del HTML fuente. No hay pipeline de assets separado.

### Persistencia crítica

- **`posts.tag_primary`** — evita re-taggear en cada build. Solo posts nuevos van a Gemini.
- **`posts.media_url_local`** — path **absoluto** (empieza con `/`) a `/assets/thumbs/`. Los archivos JPEG viven en el repo (commiteados). GitHub Pages los sirve. Si falta el `/` inicial, el browser resuelve como relativo desde `/2026-MM/` → 404 → imagen rota.
- **`periods` table** — controla el dropdown del reporte. Cada periodo listado aparece automáticamente en el selector.

## Costos operativos

| Recurso | Costo |
|---|---|
| GitHub (repo público) | $0 |
| GitHub Pages | $0 |
| Supabase (free tier) | $0 (pausa tras 7 días inactivo — mitigado por `keepalive_supabase.yml`) |
| Gemini 2.5 Flash | $0 (free tier: 250 RPD, 1M TPM) |
| Apify scraping mensual | ~$0.60-0.80 USD/mes (después del fix TT baja ~$0.30) |
| **Total mensual** | **~$0.60 USD** |

Detalle Apify (aproximado por corrida):
- Instagram: $0.20
- Facebook page: $0.20
- Facebook posts: $0.40
- TikTok profile: $0.20 (único activo)
- LinkedIn: $0.50
- Total cap por corrida: $2.10 (pero uso real ~$0.60)

## Decisiones arquitectónicas

- **Static site + JSON embebido** en lugar de dynamic Supabase fetch en el front. Elimina toda una clase de bugs de red, cache, CORS, tokens en el cliente.
- **Tags persistidos** para evitar re-consumir tokens Gemini innecesariamente.
- **Thumbnails locales** para evitar rot de URLs CDN de IG/FB (expiran en horas).
- **Un solo build parametrizado** en lugar de N workflows por periodo — nuevos meses aparecen automáticamente con solo insertar la fila en `periods`.
- **Zona horaria Bogotá** en todas las agregaciones por consistencia con el equipo local.
- **TikTok con un solo actor** (`tiktok-profile-scraper`) — el otro actor de clockworks devuelve dataset stale intermitente y no se puede confiar en él.

## Workflows

3 workflows activos, definidos en `.github/workflows/`:

| Workflow | Trigger | Función |
|---|---|---|
| `ingest_monthly.yml` | Manual (`workflow_dispatch`) | Ingesta desde Apify → Supabase |
| `build_diagnostico_extendido.yml` | Manual | Genera y publica el HTML del reporte |
| `keepalive_supabase.yml` | Cron `0 11 * * 1` (lunes 06:00 Bogotá) | Ping para que Supabase free no se pause |

Workflows eliminados 2026-07-21 (obsoletos):
- `probe_tiktok_ingest.yml` (diagnóstico puntual del bug TT)
- `rescate_tt_julio_2026.yml` (one-shot ya ejecutado)
