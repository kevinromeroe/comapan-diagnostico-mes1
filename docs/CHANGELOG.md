# CHANGELOG — Cambios notables

## 2026-07-21 · Fix estructural TT + limpieza + docs

### Fix crítico TikTok
- **Bug (recurrente)**: `clockworks/tiktok-scraper` (`GdWCkxBtKWOsKjdch`) devolvía dataset stale intermitente — no veía los posts publicados en los últimos días.
- **Fix (commit `305aa87`)**: `ingest_monthly.py` ahora usa **solo** `clockworks/tiktok-profile-scraper` (`0FXVyOXXEmdGcV88a`). Ese actor retorna cuenta + posts frescos en un mismo dataset. Se eliminó la llamada al posts-scraper y su lógica de retry.
- **Beneficios**: (a) posts siempre frescos, (b) ahorra ~$0.30 USD/mes de la llamada al segundo actor.

### Fix Heatmap
- **Bug (commit `b91dfa8`)**: `enrich_by_day_hour_heatmap` no filtraba por periodo — agregaba TODOS los posts históricos del cliente. El heatmap de julio mostraba engagement del sándwich viral de enero (9.748 en Sáb 18h).
- **Fix**: filtrar posts a `VENTANA_DESDE`/`VENTANA_HASTA` (Bogotá) antes de agregar. Aplica a todos los períodos.

### Fix ruta miniaturas
- **Bug (vía SQL)**: las 3 miniaturas TT julio se guardaron con path relativo `assets/thumbs/tt_...jpg` sin `/` inicial. Browser desde `/2026-07/` resolvía a `/2026-07/assets/thumbs/...` → 404.
- **Fix**: `UPDATE posts SET media_url_local = '/' || media_url_local WHERE ...`. Convención: siempre path absoluto con `/` inicial.

### Limpieza
- Eliminados 2 workflows one-shot: `probe_tiktok_ingest.yml`, `rescate_tt_julio_2026.yml`.
- Actualizada documentación:
  - `RUNBOOK.md` con troubleshooting de los 4 bugs históricos
  - `ARCHITECTURE.md` sin referencias a `ingest_junio_full` (ya renombrado)
  - `apify_schemas/tiktok.md` reescrito para reflejar el actor único
  - Nuevos: `SETUP_LOCAL_DEV.md`, `INCIDENTS_PLAYBOOK.md`, `ONBOARDING_CLIENT.md`, `ENGINEERING_HANDBOOK.md`

---

## 2026-07-16 · Sesión de rescate julio

### Contexto
El primer ingest de julio devolvió 0 posts TT pero había 3 visibles en la app. Investigación reveló que el actor `clockworks/tiktok-scraper` retornaba dataset stale.

### Acciones
- Rescate manual de los 3 posts TT vía SQL directo a Supabase.
- Workflow one-shot `rescate_tt_julio_2026.yml` para descargar las 3 miniaturas desde el dataset del profile-scraper vía Apify Dataset API.
- Fix heatmap descrito arriba.
- Fix path miniaturas descrito arriba.

## Junio-Julio 2026 · Sesión de mejoras extensa

### Estructura de datos
- Extensión del diagnóstico de Feb-Abr a Ene-May 2026 (298 posts vs 164 originales).
- Persistencia de tags en Supabase (`posts.tags`, `posts.tag_primary`, `posts.tagged_at`) para evitar re-consumir Gemini.
- Persistencia de thumbnails locales (`posts.media_url_local`, `posts.thumbnail_downloaded_at`) para evitar CDN rot.
- Junio 2026 ingerido con 38 posts (IG 19, FB 12, LI 5, TT 2).

### Reporte
- **Nuevo tab "Análisis por categorías"**: mix global, performance por categoría (mean/median/p75), heatmap categoría×red, heatmap categoría×tipo, gaps estratégicos.
- **Nuevo tab "Conclusiones y plan de acción"** (unificación de Hallazgos + Recomendaciones anteriores).
- **Sección "Análisis por publicación" con 3 tablas por red**: atípicos (engagement > 5× mediana), top 5 (sin atípicos), peores 5. Lógica adaptativa: si n_posts ≤ 5, solo se muestra el top.
- **Columna "Categoría" en las tablas de posts** con pills coloreados por red (primary + secondaries).
- **Deltas MoM en KPIs** — badges verdes ↑ / rojos ↓ / grises ▬ al lado de cada métrica. Solo aparecen en meses (no en diagnóstico baseline).
- **Resumen ejecutivo dinámico por periodo** (ya no hardcoded).
- **Heatmap día×hora** con hallazgo automático (mejor ventana + franjas sub-aprovechadas).
- **Charts de hora**: barras de volumen + línea de engagement promedio.
- **Charts de cada red usan solo posts típicos** (excluyen atípicos) para evitar distorsión, con disclaimer.

### UX
- Menú de redes sticky al hacer scroll.
- Topbar reordenado: Comapan (grande) → título → Catorce Días.
- PDF orientación horizontal.
- Imágenes de top posts 120px (vs 56px original).
- Rutas absolutas para assets (`/assets/...`) — sirven correctamente desde cualquier subruta.
- Placeholder de imágenes rotas con gradiente crema + ícono Comapan (no más ícono roto del browser).
- Tab "Categorías" auto-oculto si el periodo tiene menos de 3 categorías detectadas.

### Fixes de infraestructura
- Fallback inteligente para Gemini: si un batch falla, keyword matching sobre caption antes de recurrir a "marca".
- Prompt reforzado con reglas explícitas (producto vs marca vs receta, etc.).
- Build parametrizado con `--period all` que detecta automáticamente todos los periodos en Supabase.
- Ingester ahora descarga thumbnails inline (URLs CDN aún frescas). Evita el problema de expiración.

### Cleanup
- Eliminados 3 workflows one-shot (download_thumbnails, load_junio_from_datasets, rescue_thumbnails).
- Eliminados 4 scripts huérfanos.
- Eliminado `data/diagnostico.json` (baseline obsoleto).
- Workflows finales (post-2026-07-21): 3 (ingest_monthly, build_diagnostico_extendido, keepalive_supabase).

### Descubrimientos operacionales
- Supabase free tier pausa después de 7 días de inactividad. Reactivar con cualquier query en el SQL editor.
- URLs CDN de IG/FB expiran en 1-3 horas. Solución: descarga inmediata post-scrape.
- URLs LinkedIn duran semanas — más tolerables.
- Gemini 2.5 Flash usa "thinking tokens" internos. Con `thinkingConfig.thinkingBudget: 0` y `maxOutputTokens: 8000` funciona bien para batches de 25 posts.

## Julio 2026 · Cierre de operatoria semanal (pre-2026-07-21)

### Estructura
- Ingest workflow renombrado a `ingest_monthly.yml` (antes junio-específico).
- Script renombrado a `ingest_monthly.py`.
- Agregado `keepalive_supabase.yml` con cron semanal para prevenir auto-pause.

### Fix crítico
- Bug: el ingest descargaba thumbnails al runner efímero de GitHub Actions pero no los commiteaba al repo. Los HTML apuntaban a archivos inexistentes → imágenes rotas.
- Fix: nuevo step `Commit thumbnails al repo` con permissions write al final de cada ingest.
