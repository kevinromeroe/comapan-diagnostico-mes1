# CHANGELOG — Cambios notables

## Junio-Julio 2026 (sesión de mejoras extensa)

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
- Actor `clockworks/tiktok-scraper` requirió agregar 15 campos nuevos a su input (schema cambió el 30-jun-2026).
- Fallback inteligente para Gemini: si un batch falla, keyword matching sobre caption antes de recurrir a "marca".
- Prompt reforzado con reglas explícitas (producto vs marca vs receta, etc.).
- Build parametrizado con `--period all` que detecta automáticamente todos los periodos en Supabase.
- Ingester ahora descarga thumbnails inline (URLs CDN aún frescas). Evita el problema de expiración.

### Cleanup
- Eliminados 3 workflows one-shot (download_thumbnails, load_junio_from_datasets, rescue_thumbnails).
- Eliminados 4 scripts huérfanos.
- Eliminado `data/diagnostico.json` (baseline obsoleto).
- Eliminados docs obsoletos (INSIGHTS_FRAMEWORK, ONBOARDING_CLIENT).
- Workflows finales: 2 (build + ingest mensual).
- Scripts finales: 5 (build, ingest, 3 librerías).

### Descubrimientos operacionales
- Supabase free tier pausa después de 7 días de inactividad. Reactivar con cualquier query en el SQL editor.
- URLs CDN de IG/FB expiran en 1-3 horas. Solución: descarga inmediata post-scrape (implementado).
- URLs LinkedIn duran semanas — más tolerables.
- Gemini 2.5 Flash usa "thinking tokens" internos. Con `thinkingConfig.thinkingBudget: 0` y `maxOutputTokens: 8000` funciona bien para batches de 25 posts.
