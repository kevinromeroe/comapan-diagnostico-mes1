# Onboarding de un Cliente Nuevo

Procedimiento para agregar un cliente al pipeline. Estimado: **30–45 minutos** una vez tengas los accesos.

---

## Pre-requisitos del cliente

Antes de empezar, asegurarse de tener:

- [ ] Handles oficiales de Comapan / cliente en cada plataforma (IG, FB, TikTok, LinkedIn).
- [ ] Confirmar que los perfiles son públicos (Apify scrapea perfiles públicos).
- [ ] Identidad visual del cliente: paleta de colores, logo SVG y PNG, mascota si aplica.
- [ ] Datos del contacto comercial: razón social, NIT, email, teléfono.
- [ ] Acordar cadencia (quincenal/mensual) y horario del cron.
- [ ] Acordar dominio o subdominio donde se publica el reporte.

---

## Pasos

### 1. Crear el archivo de configuración del cliente

```bash
cd config/clients/
cp comapan.yaml <nombre_cliente>.yaml
```

Editar el nuevo YAML reemplazando:

- `client.id` → nuevo identificador kebab-case
- `client.name` → nombre comercial
- `client.agency` → datos de la agencia (si aplica) o el propio cliente
- `client.deploy.repo` → nuevo repo donde se publica
- `client.deploy.domain` → dominio
- `branding.*` → paleta del cliente nuevo
- `platforms.*.handle` y `platforms.*.url` → cuentas del cliente
- `platforms.*.apify.*.input` → ajustar inputs con los handles correctos

### 2. Crear el repo público del cliente

En GitHub: nuevo repo público con el nombre acordado. NO inicializar con README.
Agregar el `CNAME` con el dominio del cliente.

```bash
echo "tudominio.datalitica.com.co" > CNAME
```

Configurar GitHub Pages: Settings → Pages → Source: main branch / root.
Apuntar DNS: CNAME del dominio del cliente → `<usuario>.github.io`.

### 3. Configurar los actores en Apify

En `console.apify.com`:

1. Por cada plataforma del YAML, ir al actor correspondiente.
2. Crear una "task" con el input definido en el YAML (resultsLimit, profiles, etc.).
3. Probar el actor con un "Run" manual. Validar que devuelve datos esperados.
4. Anotar el `actId` y el `defaultDatasetId` de cada task — actualizar el YAML si difieren.

### 4. Configurar el schedule en Apify

En `console.apify.com → Schedules`:

1. Crear nuevo schedule.
2. Cron según `client.cron_utc` del YAML.
3. Agregar las 6 tasks (una por actor).
4. En "Webhooks" de cada task, agregar:
   ```
   URL: https://api.github.com/repos/<usuario>/<repo_cliente>/dispatches
   Method: POST
   Headers:
     Accept: application/vnd.github.v3+json
     Authorization: Bearer <GH_DEPLOY_TOKEN del nuevo cliente>
   Body:
     {"event_type": "apify_run_succeeded",
      "client_payload": {"client": "<cliente_id>",
                         "run_id": "{{runId}}",
                         "dataset_id": "{{defaultDatasetId}}"}}
   ```

### 5. Configurar secrets en el repo nuevo

En `Settings → Secrets and variables → Actions`:

- `APIFY_TOKEN` (puede ser el mismo que Comapan si el usuario es el mismo)
- `GH_DEPLOY_TOKEN` (PAT específico para el nuevo repo)
- `ANTHROPIC_API_KEY` (compartido, lo mismo)
- `SMTP_USER` y `SMTP_PASSWORD` (notificaciones)

### 6. Crear el workflow del cliente

Copiar `.github/workflows/pipeline.yml` a `.github/workflows/<cliente>.yml`.
Cambiar la línea `--client comapan` por el nuevo `client_id`.
Commit y push al repo del cliente nuevo.

### 7. Validar con un manual run

En el repo nuevo → Actions → Run workflow.
Verificar que:

- [ ] Los 6 actores corrieron.
- [ ] El JSON se generó correctamente.
- [ ] Los thumbs se descargaron.
- [ ] El HTML se publicó.
- [ ] El sitio carga en el dominio configurado.
- [ ] El email de notificación llegó.

### 8. Entregar al cliente

- Compartir el URL con quien corresponda (cliente / agencia).
- Enviar primer reporte de prueba para validación de marca.
- Confirmar fecha del primer run automático real.

---

## Checklist final

Antes de marcar al cliente como "en producción":

- [ ] Manual run exitoso de extremo a extremo.
- [ ] Schedule de Apify activo.
- [ ] Webhooks configurados.
- [ ] Secrets en GitHub.
- [ ] DNS apuntando correctamente.
- [ ] Notificación llega.
- [ ] Documentación del cliente en `docs/clients/<cliente>.md` (notas operacionales específicas).

---

## Costos esperados por cliente nuevo

Asumiendo volumen similar a Comapan:

| Concepto | Mensual |
|---|---|
| Apify (6 actores quincenal) | ~$0.42 USD |
| GitHub Actions | gratis (dentro de los 2.000 min/mes del free) |
| GitHub Pages | gratis |
| Anthropic API (hallazgos) | ~$0.50 USD por run, 2/mes = ~$1 USD |
| **Total** | **~$1.50 USD/mes** |

Con un fee mensual al cliente de $1.000.000 COP (~$240 USD), el margen es saludable.
