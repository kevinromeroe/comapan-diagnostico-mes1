# ENGINEERING HANDBOOK · Comapan Diagnóstico

Punto de entrada para cualquier ingeniero que trabaje en este proyecto. Este archivo es el índice y el orden de lectura recomendado.

## En 60 segundos

- **Producto:** dashboard estático (`comapan.datalitica.com.co`) con reportes mensuales de las 4 redes sociales de Comapan.
- **Pipeline:** Apify (scrape) → Supabase (persist) → Python (build) → GitHub Pages (deploy).
- **Frecuencia:** actualización mensual manual (2 clicks en GitHub Actions).
- **Stack:** Python 3.11 · Supabase Postgres · Gemini 2.5 Flash · Chart.js · GitHub Actions · Apify.
- **Costo:** ~$0.60 USD/mes.
- **Owner técnico:** Kevin Romero.

## Orden de lectura recomendado

Si acabas de entrar al proyecto, lee los docs en este orden:

1. **`README.md`** (raíz del repo) — 5 min · qué es, cómo se estructura.
2. **`docs/ARCHITECTURE.md`** — 10 min · diagrama de flujo, componentes clave, decisiones arquitectónicas.
3. **`docs/DATA_DICTIONARY.md`** — 10 min · schema Supabase y shape del DATA embebido en el HTML.
4. **`docs/SETUP_LOCAL_DEV.md`** — 15 min hands-on · clonar, instalar, correr tests, correr build local.
5. **`docs/RUNBOOK.md`** — 10 min · operativa mensual y troubleshooting de bugs conocidos.
6. **`docs/apify_schemas/*.md`** — 15 min · schema output de cada actor Apify (IG, FB, TT, LI).
7. **`docs/CHANGELOG.md`** — 5 min · historial de cambios y fixes (útil para no repetir errores).
8. **`docs/INCIDENTS_PLAYBOOK.md`** — 10 min · respuesta a incidentes comunes.
9. **`docs/ONBOARDING_CLIENT.md`** — 15 min · cómo agregar un cliente adicional al pipeline.

Total: ~90 min de lectura para estar operacional. Después de eso, puedes correr una ingesta y un build de prueba local.

## Índice completo de la documentación

| Doc | Propósito | Audiencia |
|---|---|---|
| `README.md` | Descripción de alto nivel | Todos |
| `docs/ARCHITECTURE.md` | Arquitectura técnica, flujo, componentes | Ingeniero |
| `docs/DATA_DICTIONARY.md` | Schema Supabase + shape DATA HTML | Ingeniero, analista |
| `docs/SETUP_LOCAL_DEV.md` | Cómo poner el proyecto a correr local | Ingeniero |
| `docs/RUNBOOK.md` | Operativa mensual + troubleshooting | Ingeniero, ops |
| `docs/CHANGELOG.md` | Historial de cambios | Todos |
| `docs/INCIDENTS_PLAYBOOK.md` | Respuesta a incidentes | Ingeniero de guardia |
| `docs/ONBOARDING_CLIENT.md` | Cómo agregar cliente #2 | Ingeniero, PM |
| `docs/apify_schemas/instagram.md` | Schema del actor IG | Ingeniero |
| `docs/apify_schemas/facebook.md` | Schema del actor FB | Ingeniero |
| `docs/apify_schemas/tiktok.md` | Schema del actor TT + nota deprecación | Ingeniero |
| `docs/apify_schemas/linkedin.md` | Schema del actor LI | Ingeniero |

## Tareas comunes — quick reference

### Actualizar el dashboard este mes

1. Actions → **Ingest mensual** → Run workflow (~3 min)
2. Actions → **Build diagnóstico extendido HTML** → Run workflow (~3 min)
3. Verificar `https://comapan.datalitica.com.co/<mes-actual>/`

### Debuggear un post que falta

1. Revisar logs del último `ingest_monthly.yml` run — ¿el actor lo trajo?
2. Query Supabase: `SELECT id, posted_at FROM posts WHERE client_id='comapan' AND platform='<red>' ORDER BY posted_at DESC LIMIT 20;`
3. Si Supabase lo tiene pero el HTML no lo muestra: es bug del build (ver `INCIDENTS_PLAYBOOK.md#4`).
4. Si Supabase NO lo tiene: es bug del ingest (ver `INCIDENTS_PLAYBOOK.md#3`).

### Agregar un cliente nuevo

Seguir `docs/ONBOARDING_CLIENT.md` paso a paso.

### Responder a una caída del sitio

Seguir `docs/INCIDENTS_PLAYBOOK.md#1`.

## Decisiones que un ingeniero nuevo NO debe tomar sin discutir

- **Cambiar el actor de TikTok** — el actual (`clockworks/tiktok-profile-scraper` ID `0FXVyOXXEmdGcV88a`) es el único que ha probado ser confiable. El otro (`clockworks/tiktok-scraper`) está deprecado por razones documentadas en `apify_schemas/tiktok.md`.
- **Cambiar la zona horaria** — todo el sistema opera en `America/Bogota` por consistencia con el equipo del cliente. Cambiar esto rompe deltas MoM y heatmaps.
- **Cambiar la columna `posts.media_url_local` a otra** — el schema documenta `thumb_local` como legacy; el build usa `media_url_local`. Renombrar requiere migración de datos + cambio en 3 archivos.
- **Cambiar el schema de `periods`** — la PK es `id` global (no compuesta). Ver limitación en `ONBOARDING_CLIENT.md`.

## Bugs históricos importantes de recordar (no repetir)

Ver `CHANGELOG.md` para detalle completo. Highlights:

1. **TT scraper stale** (2026-07-16, 2026-07-21) — resuelto usando solo profile-scraper.
2. **Heatmap agregaba histórico** (2026-07-16 commit `b91dfa8`) — resuelto filtrando al período.
3. **Rutas de miniatura sin `/`** (2026-07-16) — resuelto por convención: siempre path absoluto.
4. **Column name confusion** (`thumb_local` vs `media_url_local`) — código usa `media_url_local`. Schema.sql tiene `thumb_local` documentado como legacy.
5. **Thumbnails no commiteados al repo** (fix pre-2026-07-21) — resuelto con step de commit al final del ingest.
6. **Período no existe en tabla `periods`** — la ingesta fallaba silenciosamente si el mes no estaba en `periods`. Actualmente mitigado porque el fix TT no requiere aggregates/accounts para posts, pero es buena práctica insertar el período antes de ingerir.

## Entorno de trabajo con IA

Este proyecto ha sido co-desarrollado extensamente con IA (Claude). Si trabajas con IA:

- **Al abrir sesión nueva, entrégale este handbook + `RUNBOOK.md`** como contexto inicial. Evita re-descubrir los bugs históricos.
- **Antes de aplicar sugerencias de código:** verificar contra los tests, correr `pytest`, revisar el diff con `git diff`.
- **Nunca pegar credenciales en chat con IA.** Si necesitas hacer que la IA ejecute `git push`, usa un GitHub MCP con OAuth (no PAT plaintext).
- **La IA no puede hacer `git push` desde su sandbox** — siempre requiere que tú ejecutes los comandos en tu terminal.

## Contactos

- **Owner técnico:** Kevin Romero — `kevinandresromero@gmail.com` — GitHub `@kevinromeroe`
- **Cliente principal:** Comapan (vía Catorce Días — `steph@catorcedias.com`)
- **Datalítica (facturación):** Colombia S.A.S.

## Estado actual del proyecto (a 2026-07-21)

- ✅ Pipeline funcional end-to-end.
- ✅ 2 períodos publicados: `diagnostico` (Ene-May) y `2026-07`.
- ✅ Bugs TT y heatmap resueltos.
- ✅ Workflows limpios (3 activos, 2 borrados).
- ✅ Documentación completa (esta iteración).
- 🔜 Próximo período: `2026-08` (agosto). Disparar el 1 de agosto.
- 🔜 Pendiente: refactor multi-cliente completo (`CLIENT_ID` hardcoded en varios lugares).

## Handoff sugerido para un nuevo ingeniero

Semana 1:
- Lee los docs en el orden recomendado.
- Setup local dev + corre tests.
- Corre un build local en `--period diagnostico` para ver el output.

Semana 2:
- Ejecuta un ciclo completo Ingest → Build para el mes actual.
- Familiarízate con Supabase Editor y con Apify Console.
- Lee todo el código de `scripts/ingest_monthly.py` y `scripts/build_diagnostico_extendido_html.py`.

Semana 3+:
- Toma ownership de la operativa mensual.
- Prioriza el refactor multi-cliente si viene cliente #2.
- Considera migrar el schema de `periods` a PK compuesta.
