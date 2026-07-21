# RUNBOOK · Comapan Diagnóstico

Guía operativa del dashboard `comapan.datalitica.com.co`. Referencia rápida para actualizaciones mensuales, verificaciones y bugs recurrentes.

---

## 1. Actualización mensual del dashboard

El flujo base son **2 workflows manuales** en secuencia:

1. **Actions → Ingest mensual → Run workflow** (~3 min)
   Trae data fresca de Apify (IG, FB, TikTok, LinkedIn) al mes actual (Bogotá TZ), la persiste en Supabase, descarga miniaturas.

2. **Actions → Build diagnóstico extendido HTML → Run workflow** (~3 min)
   Lee Supabase, recomputa agregados/heatmaps por período, taggea con Gemini, publica en `comapan.datalitica.com.co/<mes-actual>/`.

3. **Verificación:** abrir `https://comapan.datalitica.com.co/<mes>/` — validar KPIs, miniaturas y heatmap.

---

## 2. Workflows activos

| Workflow | Trigger | Función |
|---|---|---|
| `ingest_monthly.yml` | Manual | Ingesta desde Apify → Supabase |
| `build_diagnostico_extendido.yml` | Manual | Genera y publica el HTML del reporte |
| `keepalive_supabase.yml` | Cron lunes 06:00 Bogotá | Ping para que Supabase free no se pause |

**Workflows eliminados 2026-07-21** (obsoletos, ya no son necesarios):
- `probe_tiktok_ingest.yml` (diagnóstico puntual del bug TT)
- `rescate_tt_julio_2026.yml` (one-shot ejecutado)

---

## 3. Actores de Apify

| Plataforma | Actor | ID | Estado |
|---|---|---|---|
| Instagram | `apify/instagram-scraper` | — | ✅ estable |
| Facebook pages | `apify/facebook-pages-scraper` | — | ✅ estable |
| Facebook posts | `apify/facebook-posts-scraper` | — | ✅ estable |
| **TikTok** | **`clockworks/tiktok-profile-scraper`** | **`0FXVyOXXEmdGcV88a`** | ✅ **único activo** |
| LinkedIn | `harvestapi/linkedin-company-posts` | — | ✅ estable |

**TikTok:** desde el fix del 2026-07-21, se usa **solo** `tiktok-profile-scraper`. El actor `clockworks/tiktok-scraper` (ID `GdWCkxBtKWOsKjdch`) se descartó porque devolvía dataset stale de forma intermitente. El profile-scraper retorna `account + posts` en un solo dataset fresco.

---

## 4. Verificación post-ingesta

Antes de correr el build, revisar los logs del último run de `ingest_monthly.yml`. Buscar:

```
Posts TT (via profile-scraper 0FXVyOXXEmdGcV88a): N en ventana / M totales
```

Contrastar `N` (posts en julio) contra lo que ves en la app de Comapan TikTok. Si no coincide → sección 6.

---

## 5. Convenciones importantes de Supabase

### Tabla `posts` — columnas críticas

| Columna | Uso |
|---|---|
| `id` | ID nativo de plataforma (string) |
| `media_url_local` | **Ruta absoluta** del thumbnail. Formato obligatorio: `/assets/thumbs/<archivo>.jpg` (con `/` inicial) |
| `thumb_local` | Columna documentada en `schema.sql` pero **no la usa el build**. La real es `media_url_local`. |
| `posted_at` | Timestamp UTC. Para Bogotá restar 5h. |
| `engagement` | Precalculado: `likes + comments + shares` |
| `raw` | JSONB con el item crudo de Apify |

### Reglas de negocio

- **Timezone canónica del proyecto:** `America/Bogota` (UTC-5, sin DST). Todos los filtros de período y heatmaps operan en Bogotá.
- **Outliers:** un post es outlier si `engagement > 5 × mediana del período`.
- **Categorías Gemini:** 12 tags (`producto`, `receta`, `ugc`, `estacional`, `tendencia`, `marca`, `promocional`, `educativo`, `cultura`, `interaccion`, `cobranding`, `humor`).

---

## 6. Troubleshooting — bugs históricos y cómo detectarlos

### 6.1 TT: faltan posts recientes

**Síntoma:** ves N posts en TikTok app pero el reporte muestra N-1 o N-2.

**Diagnóstico:**
1. Abrir Apify → `clockworks/tiktok-profile-scraper` → runs → último del workflow.
2. Ver los items del dataset. Buscar el post más reciente por `createTimeISO`.
3. Si el post que ves en la app **no está** en el dataset de Apify → esperar 30-60 min (posible cache de TikTok) y re-correr `ingest_monthly.yml`.
4. Si sigue faltando → correr manualmente el actor desde el Apify Console con el mismo input y comparar.

**Antipatrón (no hacer):** cambiar el actor a otro sin validación. El actual (`0FXVyOXXEmdGcV88a`) es el que ha funcionado consistentemente.

### 6.2 Miniaturas rotas en el reporte

**Síntoma:** cards de posts sin imagen (o con placeholder).

**Diagnóstico:**
```sql
SELECT id, media_url_local FROM posts
WHERE id IN (<ids afectados>);
```

**Casos:**
- `media_url_local` es `NULL` → el ingest no descargó el thumbnail. Ver logs del step "Descargar miniaturas" en `ingest_monthly.yml`.
- `media_url_local` es `"assets/thumbs/..."` (sin `/` inicial) → path relativo. Fix:
  ```sql
  UPDATE posts SET media_url_local = '/' || media_url_local
  WHERE id IN (<ids>) AND media_url_local NOT LIKE '/%';
  ```
- `media_url_local` es correcto pero el archivo no está en el repo → verificar en `assets/thumbs/`. Si falta, re-correr ingest o rescatar manual.

### 6.3 Heatmap con celdas absurdas

**Síntoma:** heatmap del período actual muestra celdas de días u horas con engagement que no cuadra con los posts del mes.

**Causa:** antes del fix `b91dfa8` el heatmap agregaba TODOS los posts históricos del cliente, no solo los del período. Si vuelve a aparecer este bug:
- Verificar que `scripts/build_diagnostico_extendido_html.py` contenga el bloque:
  ```python
  # FIX 2026-07-16: filtrar posts al periodo antes de agregarlos al heatmap.
  if VENTANA_DESDE and VENTANA_HASTA:
      ...
  ```
- Si no está, revertir a un commit posterior a `b91dfa8` o re-aplicar el fix.

### 6.4 Ingesta no persiste posts a Supabase pese a éxito de Apify

**Causa histórica:** el período (`2026-MM`) no existía en la tabla `periods`. Los FKs de `accounts` y `aggregates` fallaban silenciosamente.

**Estado actual:** este bug ya no ocurre porque el fix TT usa el profile-scraper que retorna posts + account juntos, y el ingest crea el período si falta.

**Verificación mensual (opcional, al inicio de cada mes):**
```sql
SELECT * FROM periods WHERE id = '2026-MM';
-- Si no existe:
INSERT INTO periods (id, client_id, label, starts_on, ends_on, is_baseline)
VALUES ('2026-MM', 'comapan', '<Mes> 2026', '2026-MM-01', '2026-MM-<último>', FALSE);
```

---

## 7. Datos de entorno

| Item | Valor |
|---|---|
| Repo | `github.com/kevinromeroe/comapan-diagnostico-mes1` |
| Dominio | `comapan.datalitica.com.co` (GitHub Pages via CNAME) |
| Supabase project | `pmeotakzlgkjdbwdttyf` |
| CLIENT_ID | `comapan` |
| Timezone canónica | `America/Bogota` |
| Secrets de GH Actions | `APIFY_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GEMINI_API_KEY` |

---

## 8. Historial de fixes críticos

| Fecha | Commit | Fix |
|---|---|---|
| 2026-07-16 | `b91dfa8` | Heatmap filtra por período (dejó de agregar histórico completo) |
| 2026-07-16 | `3042912` | Rescate one-shot: 3 miniaturas TT julio + `media_url_local` con `/` |
| 2026-07-16 | vía SQL | Ruta `media_url_local` con `/` absoluto (Bug 1 de julio) |
| 2026-07-21 | `305aa87` | TT usa solo `profile-scraper` + limpieza workflows + docs |

---

## 9. Contactos y contexto

- **Agencia cliente:** Catorce Días Colombia S.A.S. (marca final: Comapan)
- **Datalítica:** ejecutor técnico
- **Colaboradores frecuentes:** Claude/AI (para diagnósticos y fixes de código) — cuando trabajes con IA, siempre entregarle este RUNBOOK como contexto inicial para evitar re-descubrir bugs conocidos.

---

*Última actualización: 2026-07-21*
