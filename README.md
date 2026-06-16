# Diagnóstico Comapan — Reportería de Redes Sociales

Entregable confidencial generado por **Datalítica Colombia S.A.S.** para **Catorce Días Colombia**, sobre las cuentas digitales de **Comapan**.

© 2026 Datalítica Colombia S.A.S. — Todos los derechos reservados. El acceso, copia o distribución no autorizada de este material está prohibido.

---

## Qué es este repositorio

Este repositorio aloja dos cosas claramente separadas:

1. **El sitio publicado** en `comapan.datalitica.com.co` — los archivos en la raíz (`index.html`, `assets/`, `CNAME`) son los artefactos que GitHub Pages sirve.
2. **El pipeline ETL** que genera ese sitio automáticamente cada quincena a partir de los datos extraídos vía Apify de las plataformas de Comapan.

Los datos crudos, los CSVs, los JSONs intermedios y los scripts con credenciales **nunca** se commitean. El `.gitignore` es de tipo whitelist: solo lo explícitamente permitido entra al repo.

## Estructura

```
.
├── index.html              ⬅ deploy actual (mes 1, Ene–May 2026)
├── CNAME, robots.txt       ⬅ configuración GitHub Pages
├── assets/                 ⬅ logos, favicons, thumbnails de top posts
│
├── docs/                   ⬅ documentación viva del proyecto
│   ├── ARCHITECTURE.md
│   ├── RUNBOOK.md
│   ├── DATA_DICTIONARY.md
│   ├── INSIGHTS_FRAMEWORK.md
│   ├── ONBOARDING_CLIENT.md
│   └── apify_schemas/      ⬅ shapes de cada actor de Apify
│
├── config/                 ⬅ configuración por cliente
│   └── clients/
│       └── comapan.yaml
│
├── pipeline/               ⬅ código Python del ETL
│   ├── extract/            consume APIs de Apify y GA4
│   ├── transform/          raw → shape canónico DATA
│   ├── load/               escribe JSON + descarga thumbnails
│   ├── render/             template + DATA → HTML final
│   ├── publish/            commit + push al repo público
│   └── notify/             email/Slack al equipo
│
├── scripts/                ⬅ herramientas operacionales
├── tests/                  ⬅ tests + fixtures de respuestas Apify
└── .github/workflows/      ⬅ CI/CD: cron y manual triggers
```

## Cómo se actualiza el reporte

Cadencia: **quincenal** (días 1 y 15 de cada mes a las 06:00 hora Bogotá).

Flujo automático cuando el cron de Apify dispara:

```
Apify Schedules → corre los 6 actores en paralelo
              → webhook a GitHub Actions
GitHub Action → pipeline.extract:   descarga datasets
              → pipeline.transform: normaliza + agrega + top5
              → pipeline.load:      guarda data/YYYY-MM-DD.json (gitignored)
                                    + descarga thumbs a assets/thumbs/
              → pipeline.render:    template + DATA → index.html
              → pipeline.publish:   git commit && push
              → GitHub Pages republica automático
              → pipeline.notify:    email al equipo
```

Tiempo total: **5–8 minutos** entre el inicio del cron y el sitio actualizado.

## Cliente y cuentas analizadas

**Cliente que paga**: Catorce Días Colombia S.A.S. (NIT 901.732.649-9)
**Cuenta final analizada**: Comapan

| Plataforma | Handle |
|---|---|
| Instagram | @comapan_co |
| Facebook | ComapanCo |
| TikTok | @comapanco |
| LinkedIn | comapan-s-a- |
| Página web | comapan.com.co *(pendiente acceso GA4)* |

## Para empezar a colaborar

1. Lee `docs/ARCHITECTURE.md` para entender por qué cada cosa está donde está.
2. Lee `docs/RUNBOOK.md` para saber cómo correr el pipeline local y cómo debuggear.
3. Lee `docs/INSIGHTS_FRAMEWORK.md` para entender la rigurosidad analítica que el output debe respetar.
4. Para agregar un cliente nuevo, sigue `docs/ONBOARDING_CLIENT.md`.

## Seguridad

- Credenciales (Apify token, GitHub PAT) viven en **GitHub Secrets**, jamás en el código.
- Los datos crudos del cliente jamás se commitean — el `.gitignore` bloquea explícitamente CSVs, JSONs de data y raw responses.
- El sitio publicado tiene `robots.txt` bloqueando indexación.
- Política de rotación: Apify cada 6 meses, GitHub PAT anual.

## Stack

- **Lenguaje**: Python 3.11+
- **Orquestación**: GitHub Actions + Apify Schedules
- **Visualización**: Chart.js 4.4 (CDN), HTML estático
- **Tipografía**: Roboto Slab + Roboto (Google Fonts)
- **Deploy**: GitHub Pages con dominio custom

## Contacto

Datalítica Colombia S.A.S.
comercial@datalitica.com.co
+57 322 835 2172
