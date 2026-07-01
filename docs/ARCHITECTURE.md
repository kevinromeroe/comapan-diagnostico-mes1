# ARQUITECTURA — Reporte Comapan

## Diagrama de flujo

```
                    ┌────────────────────────┐
                    │      Apify (SaaS)      │
                    │   4 actores (IG/FB/    │
                    │      TT/LI)            │
                    └──────────┬─────────────┘
                               │ ingest_junio_full.yml
                               │ (mensual)
                               ▼
                    ┌────────────────────────┐
                    │   Supabase Postgres    │
                    │   (Comapan project)    │
                    │  ┌──────────────────┐  │
                    │  │ posts, accounts, │  │
                    │  │ aggregates, ...  │  │
                    │  └──────────────────┘  │
                    └──────────┬─────────────┘
                               │
                               │ build_diagnostico_
                               │   extendido.yml
                               │ (on-demand)
                               ▼
                    ┌────────────────────────┐
                    │  Gemini 2.5 Flash      │
                    │  (categorización)      │
                    └──────────┬─────────────┘
                               │
                               ▼
                    ┌────────────────────────┐
                    │  GitHub repo main      │
                    │  /                     │
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

### Pipeline de scraping (`scripts/ingest_junio_full.py`)

- Corre 4 actores de Apify secuencialmente con caps de seguridad.
- Filtra posts al calendario mensual (Bogotá).
- Persiste accounts, posts y aggregates en Supabase.
- **Descarga thumbnails inmediatamente** post-scrape (URLs CDN expiran en horas).
- Comprime a 400px width JPEG q60, guarda en `/assets/thumbs/`.
- Actualiza `posts.media_url_local` vía PATCH.

### Pipeline de build (`scripts/build_diagnostico_extendido_html.py`)

Genera el HTML final. Modo por defecto: `--period all` (regenera todos los periodos).

Por cada periodo:
1. Lee accounts, aggregates y posts de Supabase.
2. Split posts en atípicos (engagement > 5× mediana) y típicos.
3. Calcula aggregates de gráficas usando solo típicos.
4. Genera heatmap día×hora en zona Bogotá.
5. Tagea posts sin `tag_primary` con Gemini (12 categorías fijas). Persiste tags a Supabase.
6. Fallback keyword-based si Gemini falla (evita "marca" masivo).
7. Propaga tags a top5/atípicos/worst5 (que son copias, no refs).
8. Calcula `category_analysis` (mix, performance, heatmaps, gaps).
9. Calcula deltas MoM vs mes anterior (solo si aplica).
10. Genera resumen ejecutivo dinámico basado en la data del periodo.
11. Reemplaza `const DATA = {...}` y `const REPORT_META = {...}` en el template.
12. Escribe a `/{period}/index.html`. Diagnóstico también sobreescribe `/index.html` (landing).

### Templates

Solo hay 2 archivos vivos:
- `diagnostico/index.html` — template fuente, se auto-sobreescribe en cada build.
- `index.html` — landing (copia del diagnóstico).
- `/2026-MM/index.html` — clonado del diagnóstico + DATA reemplazado.

Todo estilo, CSS, JS reutilizable vive dentro del HTML fuente. No hay pipeline de assets separado.

### Persistencia crítica

- **`posts.tag_primary`** — evita re-taggear en cada build. Solo posts nuevos van a Gemini.
- **`posts.media_url_local`** — path relativo a `/assets/thumbs/`. Los archivos JPEG viven en el repo (commiteados). GitHub Pages los sirve.
- **`periods` table** — controla el dropdown del reporte. Cada periodo listado aparece automáticamente en el selector.

## Costos operativos

| Recurso | Costo |
|---|---|
| GitHub (repo público) | $0 |
| GitHub Pages | $0 |
| Supabase (free tier) | $0 (pausa tras 7 días inactivo) |
| Gemini 2.5 Flash | $0 (free tier: 250 RPD, 1M TPM) |
| Apify scraping mensual | ~$0.60-0.80 USD/mes |
| **Total mensual** | **~$1 USD** |

## Decisiones arquitectónicas

- **Static site + JSON embebido** en lugar de dynamic Supabase fetch en el front. Elimina toda una clase de bugs de red, cache, CORS, tokens en el cliente.
- **Tags persistidos** para evitar re-consumir tokens Gemini innecesariamente.
- **Thumbnails locales** para evitar rot de URLs CDN de IG/FB (expiran en horas).
- **Un solo build parametrizado** en lugar de N workflows por periodo — nuevos meses aparecen automáticamente con solo insertar la fila en `periods`.
- **Zona horaria Bogotá** en todas las agregaciones por consistencia con el equipo local.
