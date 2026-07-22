# PLAYBOOK · Respuesta a incidentes

Protocolo de respuesta para las fallas más comunes. Cada sección: **síntoma → diagnóstico → fix**.

## 1. Sitio caído — 404 o error del proxy

**Síntoma:** `https://comapan.datalitica.com.co/` devuelve 404, 403, timeout o página en blanco.

**Diagnóstico rápido:**
1. Abrir directamente el repo `github.com/kevinromeroe/comapan-diagnostico-mes1` — ¿existen `index.html`, `diagnostico/index.html`?
2. Revisar `Actions → pages-build-deployment` — ¿el último run fue exitoso?
3. Verificar `CNAME` — debe contener exactamente `comapan.datalitica.com.co`
4. Verificar DNS del dominio (fuera de nuestro control — depende del owner del dominio `datalitica.com.co`)

**Fix:**
- Si el último `pages-build-deployment` falló: mirar logs, buscar error de sintaxis en HTML, y hacer un commit vacío para forzar re-deploy: `git commit --allow-empty -m "chore: trigger pages redeploy" && git push`
- Si CNAME está mal: `echo 'comapan.datalitica.com.co' > CNAME && git commit -am "fix: restore CNAME" && git push`
- Si DNS no resuelve: fuera de alcance del proyecto. Contactar owner de `datalitica.com.co`.

## 2. Todas las miniaturas rotas en un período

**Síntoma:** al abrir `/2026-MM/` todas las tarjetas de posts muestran placeholder o imagen rota.

**Diagnóstico:**
```sql
SELECT id, platform, media_url_local
FROM posts
WHERE client_id = 'comapan'
  AND posted_at >= '2026-MM-01'
  AND posted_at <  '2026-MM-<siguiente>-01'
ORDER BY platform;
```

**Casos y fix:**

| Caso | Causa | Fix |
|---|---|---|
| `media_url_local` es `NULL` para todos | Ingest no descargó thumbnails | Verificar logs de `ingest_monthly.yml` en step "Descargar miniaturas". Re-correr el workflow. |
| `media_url_local` no empieza con `/` | Path relativo mal grabado | `UPDATE posts SET media_url_local = '/' \|\| media_url_local WHERE ... AND media_url_local NOT LIKE '/%';` |
| Paths correctos pero archivos no existen en repo | Ingest descargó pero no commiteó | Ver Bug histórico documentado, ya corregido. Re-correr ingest debe re-descargar y commitear. |
| Solo TT roto | Cover URL vencido cuando se descargó | Re-correr ingest — nuevo `profile-scraper` da cover URL nueva. |

## 3. Ingesta falla — 0 posts para una plataforma

**Síntoma:** después del `Ingest mensual`, el reporte muestra 0 posts de IG/FB/TT/LI donde debería haber varios.

**Diagnóstico:**
1. Abrir Apify Console → `Actors` → click el actor de la plataforma afectada → `Runs` → último run del workflow.
2. Ver el dataset — ¿trajo items? ¿de qué fechas?

**Casos y fix:**

| Caso | Fix |
|---|---|
| Actor falló (status FAILED) | Ver mensaje de error del actor. Casos comunes: cuenta privada, IP bloqueada, límites de crédito Apify. |
| Actor OK pero 0 items | Verificar el `input` del actor — profile handle correcto? Fecha? |
| Actor OK con items pero fuera del período | Chequear timezone Bogotá vs UTC del filtro. Ver `month_window()` en `ingest_monthly.py`. |
| **TT específico:** dataset stale | Es el bug histórico. Esperar 30-60 min (cache TikTok) y re-correr `ingest_monthly.yml`. Si persiste, ver sección Bug TT en `RUNBOOK.md`. |

## 4. Build falla o produce HTML corrupto

**Síntoma:** el workflow `build_diagnostico_extendido.yml` falla, o el HTML publicado tiene errores (JS que no arranca, `${p.media_url}` sin sustituir, etc.).

**Diagnóstico:**
1. Ver logs del workflow en Actions.
2. Buscar el step que falló: `Enriquecimiento`, `Gemini`, `Deltas`, `Renderizar HTML`.

**Casos y fix:**

| Caso | Fix |
|---|---|
| `⚠ Enriquecimiento (tags+heatmap) fallo:` | Ver traceback. Si es Gemini API error, verificar `GEMINI_API_KEY` en secrets. |
| `Deltas MoM fallo:` | El período anterior no tiene aggregates. Correr `ingest_monthly.yml` para el mes anterior primero. |
| Template roto (`${p.media_url}` literal) | El template usa JS client-side. Debe ejecutarse en el browser. Verificar que el HTML tenga `const DATA = {...}` con el JSON correcto embebido. |
| Build corre pero deploy no publica | Ver `Actions → pages-build-deployment` separado. |

**Rollback rápido:**

```bash
cd ~/Desktop/comapan-diagnostico-mes1
git log --oneline | head -10       # identificar último build bueno
git revert <commit-malo>            # o git reset --hard <commit-bueno> si nadie más pusheó
git push origin main
```

## 5. Supabase pausado (7 días sin actividad)

**Síntoma:** cualquier query o el pipeline retorna error tipo "Project is paused".

**Fix:**
1. Ir a `https://supabase.com/dashboard/project/pmeotakzlgkjdbwdttyf`
2. Botón `Restore project` (o `Resume`).
3. Esperar ~2 min.

**Prevención:** el workflow `keepalive_supabase.yml` corre cada lunes 06:00 Bogotá. Si el pause vuelve a pasar, revisar que el keepalive esté activo.

## 6. Apify actor descontinuado o cambió schema

**Síntoma:** el ingest falla con error de campo inexistente, o los datos vienen con estructura distinta.

**Diagnóstico:**
1. Abrir el actor en Apify Console.
2. Leer los "Release notes" o el "Actor version history".
3. Verificar el input schema y el output schema actuales vs el documentado en `docs/apify_schemas/`.

**Fix:**
1. Actualizar `config/clients/comapan.yaml` con el nuevo input schema.
2. Actualizar `pipeline/transform/normalize.py` con el nuevo output schema.
3. Actualizar `docs/apify_schemas/<plataforma>.md`.
4. Correr tests: `pytest tests/`.
5. Correr ingest local con `--period 2026-MM` y verificar en Supabase.
6. Solo entonces mergear a `main`.

## 7. Rollback del sitio

**Si necesitas volver a un estado anterior del reporte (por publicación errónea):**

```bash
cd ~/Desktop/comapan-diagnostico-mes1
git log --oneline --all | grep "Build automatico" | head -20    # ver builds
git revert <commit-malo>                                          # revert conservador
git push origin main
```

Alternativa (más agresiva, borrar historial):

```bash
git reset --hard <commit-bueno-conocido>
git push --force-with-lease origin main
```

**Precaución:** `--force-with-lease` reescribe historia. Solo hacerlo si estás 100% seguro y avisar al equipo antes.

## 8. Secrets rotos o expirados

**Síntoma:** workflows fallan con 401/403 en Apify o Supabase.

**Fix:**
1. Ir a `github.com/kevinromeroe/comapan-diagnostico-mes1/settings/secrets/actions`
2. Rotar el secret afectado:
   - `APIFY_TOKEN` — desde Apify Console → Settings → Integrations → API tokens
   - `SUPABASE_SERVICE_KEY` — desde Supabase → Project Settings → API → service_role
   - `GEMINI_API_KEY` — desde Google AI Studio
3. Re-correr el workflow que falló.

## 9. Contactos de escalación

- **Owner técnico del repo:** Kevin Romero (kevinandresromero@gmail.com)
- **Cliente:** Catorce Días — Steph (steph@catorcedias.com, +57 315 348 0363)
- **Apify support:** support@apify.com (respuesta ~24h)
- **Supabase support:** free tier no tiene SLA, ver docs.supabase.com o Discord.
- **Google AI (Gemini):** ai.google.dev, chat con dev support en Discord o via forms.

## 10. Checklist post-incidente

Después de cada incidente:

1. Documentar el incidente en el CHANGELOG con fecha, síntoma, causa raíz, fix.
2. Si el fix requiere cambio de código: crear PR con el fix + agregar test que capturaría el bug.
3. Si es un incidente recurrente: agregar sección al `RUNBOOK.md` con el troubleshooting.
4. Actualizar este playbook si el flow de respuesta se puede mejorar.
