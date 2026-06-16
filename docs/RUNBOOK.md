# Runbook Operacional

Manual práctico para correr, debuggear y mantener el pipeline. Si algo se rompe a las 3am, este doc tiene la respuesta.

---

## Setup inicial local (una sola vez)

```bash
# Clonar el repo
git clone https://github.com/kevinromeroe/comapan-diagnostico-mes1.git
cd comapan-diagnostico-mes1

# Crear venv
python3.11 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt

# Copiar plantilla de variables y rellenar
cp .env.example .env.local
# Editar .env.local con tus tokens reales
```

`.env.local` está en `.gitignore` y nunca se commitea.

---

## Correr el pipeline localmente

```bash
# Cargar variables de entorno
set -a; source .env.local; set +a

# Correr para Comapan
python -m pipeline.run --client comapan --period $(date +%Y-%m-%d)

# Correr en modo dry-run (no pushea al repo público)
python -m pipeline.run --client comapan --dry-run
```

Outputs esperados:
- `data/2026-MM-DD.json` (gitignored): el DATA generado.
- `assets/thumbs/*.jpg` (versionado): nuevas miniaturas si hubo posts nuevos.
- `index.html` regenerado: el reporte listo para deploy.
- Log JSON estructurado en stdout.

---

## Inspeccionar shapes de Apify

Cuando un actor cambia o queremos validar qué devuelve hoy:

```bash
# Listar los runs recientes sin descargar nada
python scripts/inspect_apify.py --list-runs

# Mapear un dataset específico
python scripts/inspect_apify.py --dataset QPFngkHiDgeV8gZka

# Mapear todos los datasets de runs recientes y guardar como fixtures
python scripts/inspect_apify.py --save-fixtures
```

Los fixtures quedan en `tests/fixtures/` y se commitean para que los tests siempre tengan data real contra la cual correr.

---

## Trigger manual desde GitHub Actions

Para regenerar un reporte sin esperar al cron:

1. Ir a `Actions` en el repo en GitHub.
2. Seleccionar el workflow "Pipeline (manual)".
3. Click en "Run workflow".
4. Inputs:
   - `client`: comapan
   - `period`: 2026-06-15 (o la fecha que quieras forzar)
5. Run.

Útil para:
- Regenerar el reporte con data corregida.
- Probar cambios al pipeline antes del próximo cron.
- Generar un reporte ad-hoc para una fecha pasada.

---

## Configurar el Apify Schedule

Una sola vez, en `console.apify.com`:

1. Schedules → Create schedule.
2. Cron: `0 11 1,15 * *` (UTC = 06:00 Bogotá los días 1 y 15).
3. Actor: agregar uno por uno los 6 actores con su input correspondiente desde `config/clients/comapan.yaml`.
4. Webhooks (por cada actor): on success → POST a:
   ```
   https://api.github.com/repos/kevinromeroe/comapan-diagnostico-mes1/dispatches
   ```
   Con headers:
   ```
   Accept: application/vnd.github.v3+json
   Authorization: Bearer <GH_DEPLOY_TOKEN>
   ```
   Body JSON:
   ```json
   {"event_type": "apify_run_succeeded",
    "client_payload": {"run_id": "{{runId}}", "dataset_id": "{{defaultDatasetId}}"}}
   ```

El workflow `.github/workflows/pipeline.yml` está configurado para escuchar este `repository_dispatch`.

---

## Qué hacer si...

### El cron de Apify no disparó

1. Verificar en `console.apify.com → Schedules` que el schedule esté **enabled**.
2. Ver el log del último intento — Apify guarda historial.
3. Si fue un error de credenciales, regenerar el token y actualizar `APIFY_TOKEN` en GitHub Secrets.

### Un actor falló

1. En `console.apify.com → Actor runs` ver el log del run fallido.
2. Causas frecuentes:
   - **Cuenta cambió de visibilidad**: el handle ahora es privado o fue eliminado.
   - **Rate limit del actor**: TikTok especialmente sensible; esperar 1 hora y reintentar.
   - **Plataforma cambió HTML**: el actor necesita actualización del developer (apify/clockworks/harvestapi).
3. El pipeline está diseñado para NO abortar: las demás plataformas siguen y el reporte se publica con marca de "data incompleta para X".

### El push al repo público falla

1. Verificar que el `GH_DEPLOY_TOKEN` no haya expirado (rotar a más tardar 14-sep-2026).
2. Verificar que el token tenga scope `Contents: Read and write` sobre el repo correcto.
3. Si el push falla por conflict (alguien commiteó manualmente), el workflow hace pull + rebase + push retry.

### El HTML generado se ve roto

1. Reproducir local: `python -m pipeline.run --client comapan --dry-run`.
2. Abrir el `index.html` resultante en navegador.
3. Si Chart.js no renderiza: verificar que el `DATA` inyectado sea JSON válido (sin saltos de línea sueltos en strings).
4. Si los thumbs salen rotos: verificar que `assets/thumbs/<hash>.jpg` exista para cada `top5.media_url`.

### Claude no genera hallazgos válidos

1. Verificar `ANTHROPIC_API_KEY` en GitHub Secrets.
2. Ver log: el pipeline reintenta 3 veces con prompt cada vez más estricto.
3. Si los 3 intentos fallan schema, el reporte se publica con sección de hallazgos manual (placeholder "Pendiente análisis humano").
4. Editar prompt en `pipeline/transform/insights_llm.py` según el patrón de error.

### El reporte salió pero faltan métricas

1. Causa #1: el actor devolvió menos posts de los esperados → aumentar `resultsLimit` en `comapan.yaml`.
2. Causa #2: la ventana de análisis dejó posts fuera → revisar `window_days` en el YAML.
3. Causa #3: bug en el transform → correr tests y verificar contra fixture.

---

## Rotación de credenciales

| Credencial | Frecuencia | Cómo rotar |
|---|---|---|
| `APIFY_TOKEN` | Cada 6 meses | console.apify.com → Settings → Tokens → revoke + create + actualizar GitHub Secret |
| `GH_DEPLOY_TOKEN` | Anual (vence 14-sep-2026) | github.com/settings/tokens → revoke + create + actualizar GitHub Secret |
| `GA4_SERVICE_ACCOUNT_JSON` | Cuando exista, anual | console.cloud.google.com → IAM → rotate key |
| `ANTHROPIC_API_KEY` | Anual | console.anthropic.com → API Keys → rotate |

Tras rotar: probar con un manual run antes del próximo cron automático.

---

## Métricas de salud del sistema

Cada corrida deja en el log JSON estos números clave:

```json
{
  "run_id": "...",
  "client": "comapan",
  "period": "2026-06-15",
  "duration_seconds": 348,
  "platforms": {
    "instagram": {"status": "ok", "n_posts": 33, "thumbs_downloaded": 5},
    "facebook": {"status": "ok", "n_posts": 14, "thumbs_downloaded": 5},
    "tiktok": {"status": "ok", "n_posts": 9, "thumbs_downloaded": 5},
    "linkedin": {"status": "warning", "n_posts": 0, "thumbs_downloaded": 0,
                 "message": "No posts en la ventana"}
  },
  "llm_hallazgos": {"intentos": 1, "validados": true},
  "publish": {"status": "ok", "commit_sha": "abc123"},
  "notify": {"status": "ok", "recipients": 1}
}
```

GitHub Actions guarda 90 días de historial de runs. Pasada esa ventana, los runs viejos quedan solo en commits del repo.

---

## Política de soporte (SLA interno)

| Tipo de incidente | Tiempo respuesta | Tiempo resolución |
|---|---|---|
| Reporte no se generó en su fecha | 24h hábiles | 48h hábiles |
| Hallazgos sin sustento (calidad) | 48h hábiles | 1 semana |
| Mejora solicitada por cliente | 1 semana | acordar |
| Plataforma rota (cambio de HTML) | 24h hábiles | depende del developer del actor |
