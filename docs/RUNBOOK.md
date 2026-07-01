# RUNBOOK — Operación del reporte Comapan

Guía de tareas frecuentes para operar el reporte. Todo se ejecuta desde GitHub Actions — no requiere corridas locales.

---

## Arquitectura actual

**Repositorio:** `kevinromeroe/comapan-diagnostico-mes1`
**URL en vivo:** https://comapan.datalitica.com.co/

**Fuentes de datos:**
- Apify (scraping de las 4 redes: IG, FB, TT, LI)
- Supabase Postgres (tablas: `clients`, `periods`, `accounts`, `posts`, `aggregates`, `summaries`, `hallazgos`)
- Gemini 2.5 Flash (tagging de categorías, free tier)

**Deploy:** GitHub Pages → `main` branch. Todo cambio en `main` se despliega en ~30-60s.

**Estructura del sitio:**
- `/` — landing con el diagnóstico más reciente
- `/diagnostico/` — baseline Ene-May 2026
- `/2026-MM/` — reporte mensual (junio, julio, etc.)

---

## Workflows disponibles

Solo 2 workflows recurrentes. Todo lo demás fue eliminado (era código muerto).

### `ingest_junio_full.yml` — scrape mensual

**Cuándo:** día 1 de cada mes calendario o cuando querés data fresca.
**Costo:** ~$0.60-0.80 USD Apify (cap $3.40).
**Duración:** 5-8 min.

Corre los 4 actores, filtra a ventana del mes, persiste a Supabase (accounts + posts + aggregates), **descarga thumbnails al instante mientras las URLs CDN siguen frescas** (esto es clave — las URLs de IG/FB expiran en horas).

**Cómo:** https://github.com/kevinromeroe/comapan-diagnostico-mes1/actions/workflows/ingest_junio_full.yml → Run workflow.

### `build_diagnostico_extendido.yml` — regenerar HTML

**Cuándo:** después de un ingest, o cuando querés propagar cambios de código al reporte.
**Costo:** $0 USD (solo lecturas de Supabase + Gemini free tier).
**Duración:** 30-60s.

Input: `period` con default `all`.
- `all` → regenera diagnóstico + todos los meses en Supabase (recomendado, un solo click).
- `diagnostico` → solo el baseline.
- `2026-06`, `2026-07`, ... → un mes específico.

**Qué hace:**
1. Lee posts + accounts + aggregates de Supabase.
2. Enriquece con heatmap día×hora en zona Bogotá.
3. Llama a Gemini para tagear posts sin `tag_primary` (skip a los que ya tienen tag persistido).
4. Calcula análisis por categorías (mix, performance, heatmap categoría×red, gaps).
5. Calcula deltas MoM vs mes anterior (solo si hay mes anterior).
6. Regenera resumen ejecutivo dinámico.
7. Escribe HTML estático + commit + push.

**Cómo:** https://github.com/kevinromeroe/comapan-diagnostico-mes1/actions/workflows/build_diagnostico_extendido.yml → Run workflow.

---

## Procedimientos

### A. Ingest de un mes nuevo (ej. julio)

1. Asegurate que Supabase esté activo (si estuvo pausado por inactividad, entrar al dashboard, correr `SELECT 1;` y esperar 30s).
2. Disparar `ingest_junio_full.yml` (aunque diga junio, el script filtra por su calendario interno — para julio hay que ajustar el `PERIOD_ID` interno, ver "Extensión a mes nuevo" abajo).
3. Verificar en Supabase con:
   ```sql
   SELECT platform, COUNT(*) AS n
   FROM posts
   WHERE client_id='comapan'
     AND posted_at >= '2026-07-01' AND posted_at <= '2026-07-31 23:59:59'
   GROUP BY platform;
   ```
4. Disparar `build_diagnostico_extendido.yml` con `period=all` (o `2026-07` solo).
5. Verificar visualmente el reporte en `https://comapan.datalitica.com.co/2026-07/`.

### B. Extensión a un mes nuevo

Para julio 2026:
1. Editar `scripts/ingest_junio_full.py` (o crear una copia `ingest_julio_full.py`) cambiando `PERIOD_ID = "2026-07"` y la ventana en `june_window()` a julio.
2. Insertar el period en Supabase:
   ```sql
   INSERT INTO periods (id, client_id, label, starts_on, ends_on, is_baseline)
   VALUES ('2026-07', 'comapan', 'Julio 2026', '2026-07-01', '2026-07-31', false);
   ```
3. Correr el ingest.
4. Correr el build → el nuevo mes aparece automáticamente en el dropdown.

Alternativa más limpia: parametrizar `ingest_junio_full.py` con `--period 2026-MM`. Pendiente de refactor.

### C. Corregir tags mal clasificados

Si el equipo detecta posts mal etiquetados en el reporte:

1. Ejecutar en Supabase SQL Editor:
   ```sql
   UPDATE posts
   SET tag_primary = NULL, tags = NULL, tagged_at = NULL
   WHERE client_id = 'comapan'
     AND posted_at >= '2026-XX-01' AND posted_at <= '2026-XX-31 23:59:59';
   ```
   (Cambiar `XX` por el mes a re-tagear.)

2. Disparar el build. Gemini re-clasifica los posts sin tag.

3. Si algún post sigue clasificado como "marca" y no debería, es porque Gemini falla el batch y aplica el fallback keyword. Ver la función `_guess_tag_from_caption()` en `build_diagnostico_extendido_html.py` para ajustar keywords si hace falta.

### D. Rescatar thumbnails perdidos

Ya no debería pasar porque `ingest_junio_full.py` descarga inline. Pero si un mes viejo tiene posts con `media_url_local IS NULL` y las CDN URLs ya vencieron, no hay recuperación posible sin re-scrape (que trae URLs nuevas). Costo estimado del re-scrape: ~$0.80 USD.

### E. Supabase auto-pausado

Free tier pausa proyectos tras ~7 días sin actividad. Síntoma: workflows fallan con `Name or service not known` o timeout DNS.

**Reactivar:** abrir https://supabase.com/dashboard/project/pmeotakzlgkjdbwdttyf/sql/new y correr `SELECT NOW();`. Esperar 30-60s. Re-disparar el workflow.

**Prevención opcional:** agregar un workflow con `cron: "0 8 * * 1"` que haga `SELECT 1;` semanal.

---

## Secrets necesarios en GitHub

En Settings → Secrets → Actions:

| Secret | Valor / origen |
|---|---|
| `SUPABASE_URL` | `https://pmeotakzlgkjdbwdttyf.supabase.co` |
| `SUPABASE_SERVICE_KEY` | Service role key (Supabase dashboard → Settings → API) |
| `APIFY_TOKEN` | Personal token en Apify Console → Settings → Integrations |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey |

---

## Historial de decisiones importantes

- **Data window para el diagnóstico:** Ene-May 2026 (originalmente Feb-Abr por límite del scrape, extendido con `ingest_diagnostico_ampliado`).
- **Persistencia de tags:** en Supabase (columnas `tags` JSONB, `tag_primary` TEXT, `tagged_at` TIMESTAMPTZ). Evita re-tagear en cada build.
- **Persistencia de thumbnails:** en `/assets/thumbs/` del repo (JPEG q60 400px). Referenciados vía `posts.media_url_local`.
- **Zona horaria:** América/Bogotá (UTC-5) para todas las agregaciones día/hora.
- **Regla atípicos:** engagement > 5× mediana del período (por red).
- **Fallback tagging:** cuando Gemini falla, keyword matching sobre caption antes de recurrir a "marca".
- **Deltas MoM:** aplican solo a periods no-baseline (mes vs mes anterior). Diagnostico → sin deltas.
