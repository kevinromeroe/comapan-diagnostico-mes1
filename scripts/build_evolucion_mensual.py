#!/usr/bin/env python3
"""Inserta/actualiza la sección "Evolución mes a mes" en el Resumen ejecutivo.

Consulta Supabase (accounts + posts), arma seguidores, interacciones y piezas
por red y mes desde enero, y reescribe el bloque entre los marcadores
EVOL-MENSUAL en diagnostico/index.html y en index.html. Idempotente.

Env vars: SUPABASE_URL, SUPABASE_SERVICE_KEY
Uso: python scripts/build_evolucion_mensual.py
"""
from __future__ import annotations

import calendar
import json
import ssl
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

try:
    import certifi
    ssl._create_default_https_context = lambda *a, **k: ssl.create_default_context(cafile=certifi.where())
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.load.supabase_client import Supabase  # noqa: E402

CLIENT_ID = "comapan"
YEAR_START = "2026-01"
# La sección se muestra en la página inicial y en todos los reportes mensuales.
TARGETS = [ROOT / "diagnostico" / "index.html", ROOT / "index.html",
           *sorted(ROOT.glob("20[0-9][0-9]-[01][0-9]/index.html"))]
PAID_FILE = ROOT / "config" / "clients" / "comapan_piezas_pauta.json"
EXTRA_FOLLOWERS_FILE = ROOT / "config" / "clients" / "comapan_seguidores_extra.json"
START = "<!-- EVOL-MENSUAL:START -->"
END = "<!-- EVOL-MENSUAL:END -->"
# Punto de inserción la primera vez: después de la tabla "Las cuatro cuentas" del Resumen ejecutivo.
ANCHOR = '<tbody id="t-accounts"></tbody>\n    </table>\n  </div>\n'

NETS = ["ig", "fb", "tt", "li"]
PLATFORM_KEY = {"instagram": "ig", "facebook": "fb", "tiktok": "tt", "linkedin": "li"}
MES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def fetch_all(sb: Supabase, path: str) -> list[dict]:
    rows, offset = [], 0
    while True:
        batch = sb._request("GET", f"{path}&limit=1000&offset={offset}")
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def month_range(first: str, last: str) -> list[str]:
    y, m = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def build_data(sb: Supabase) -> dict:
    accounts = fetch_all(sb, f"/accounts?client_id=eq.{CLIENT_ID}&select=period_id,platform,followers,snapshot_at")
    posts = fetch_all(sb, f"/posts?client_id=eq.{CLIENT_ID}&select=id,platform,posted_at,engagement")
    paid_ids = {x["id"] for x in json.loads(PAID_FILE.read_text())["piezas"]}

    latest_snap = max(date.fromisoformat(a["snapshot_at"][:10]) for a in accounts if a.get("snapshot_at"))
    last_month = max(p["posted_at"][:7] for p in posts if p.get("posted_at"))
    months = month_range(YEAR_START, last_month)

    ly, lm = map(int, last_month.split("-"))
    month_end = calendar.monthrange(ly, lm)[1]
    partial = latest_snap.year == ly and latest_snap.month == lm and latest_snap.day < month_end

    inter = {n: [0] * len(months) for n in NETS}
    pieces = {n: [0] * len(months) for n in NETS}
    for p in posts:
        k = PLATFORM_KEY.get(p.get("platform"))
        m = (p.get("posted_at") or "")[:7]
        if not k or m not in months:
            continue
        i = months.index(m)
        pieces[k][i] += 1
        # Las piezas con pauta cuentan como publicadas, pero no en interacciones orgánicas.
        if p["id"] not in paid_ids:
            inter[k][i] += int(p.get("engagement") or 0)

    # Seguidores: solo el campo followers. Se descartan cifras redondeadas a miles
    # (vienen de textos tipo "119K") porque no sirven para medir variaciones.
    foll = defaultdict(dict)
    for a in accounts:
        k = PLATFORM_KEY.get(a.get("platform"))
        v = a.get("followers")
        if not k or not v or v % 1000 == 0:
            continue
        pid = a["period_id"]
        m = a["snapshot_at"][:7] if pid == "diagnostico" else pid
        foll[k][m] = v
    # Puntos recuperados de copias archivadas del perfil (solo si ese mes no tiene corrida propia).
    for pt in json.loads(EXTRA_FOLLOWERS_FILE.read_text())["puntos"]:
        k = PLATFORM_KEY.get(pt["red"])
        if k:
            foll[k].setdefault(pt["fecha"][:7], pt["seguidores"])
    # Mismo eje que las otras gráficas; los meses sin registro quedan vacíos.
    f_months = months
    followers = {n: [foll[n].get(m) for m in f_months] for n in NETS}

    return {
        "months": [MES[int(m[5:]) - 1] for m in months],
        "partial": partial,
        "cutoffDay": latest_snap.day,
        "interactions": inter,
        "paidCount": sum(1 for p in posts if p["id"] in paid_ids and (p.get("posted_at") or "")[:7] in months),
        "pieces": pieces,
        "fMonths": [MES[int(m[5:]) - 1] for m in f_months],
        "followers": followers,
    }


def render_block(data: dict) -> str:
    first, last = data["months"][0], data["months"][-1]
    full = {"Ene": "enero", "Feb": "febrero", "Mar": "marzo", "Abr": "abril", "May": "mayo", "Jun": "junio",
            "Jul": "julio", "Ago": "agosto", "Sep": "septiembre", "Oct": "octubre", "Nov": "noviembre", "Dic": "diciembre"}
    foot_txt = f'* {full[last].capitalize()} con datos hasta el {data["cutoffDay"]}.'
    foot = f'<div class="evo-foot">{foot_txt}</div>' if data["partial"] else ""
    payload = json.dumps(data, ensure_ascii=False)
    return f"""{START}
  <div class="section-head">
    <div class="num">04 · Evolución mes a mes</div>
    <h2>Cómo se han movido las cuentas de {full[first]} a {full[last]}.</h2>
    <div class="desc">Seguidores, interacciones y piezas publicadas por red, mes a mes.</div>
  </div>
  <style>
    .evo-multiples {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }}
    .evo-mini {{ border: 1px solid var(--line); border-radius: 4px; padding: 14px 14px 10px; background: var(--bg); }}
    .evo-mini-top {{ display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500; color: var(--ink-soft); }}
    .evo-mini-top i {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; }}
    .evo-mini-val {{ font-family: 'Roboto Slab', serif; font-size: 26px; font-weight: 600; margin-top: 6px; font-variant-numeric: tabular-nums; color: var(--ink); }}
    .evo-mini-delta {{ font-size: 12px; font-weight: 500; font-variant-numeric: tabular-nums; }}
    .evo-mini-delta.up {{ color: #2f7d32; }}
    .evo-mini-delta.down {{ color: #c0392b; }}
    .evo-mini-delta span {{ color: var(--muted); font-weight: 400; }}
    .evo-mini-chart {{ position: relative; height: 90px; margin-top: 8px; }}
    .evo-foot {{ font-size: 12px; color: var(--muted); margin-top: 8px; }}
    @media (max-width: 1000px) {{ .evo-multiples {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
    @media (max-width: 520px) {{ .evo-multiples {{ grid-template-columns: 1fr; }} }}
    @media print {{ .evo-mini-chart {{ height: 80px; }} }}
  </style>
  <div class="chart-card">
    <h3>Seguidores por red <i class="info-icon" data-tip="Seguidores de cada cuenta mes a mes. Cada red se muestra en su propia escala para que las variaciones sean comparables.">i</i></h3>
    <div class="evo-multiples" id="evo-multiples"></div>
    <div class="learn" id="l-evo-followers"></div>
  </div>
  <div class="chart-card" style="margin-top:20px">
    <h3>Interacciones orgánicas al mes por red <i class="info-icon" data-tip="Interacciones = likes + comentarios + compartidos de las publicaciones hechas en cada mes. No incluye las piezas identificadas con pauta.">i</i></h3>
    <div class="chart-wrap" style="height:320px"><canvas id="c-evo-interactions"></canvas></div>
    <div class="evo-foot">No incluye {data["paidCount"]} piezas con pauta.{(" " + foot_txt) if data["partial"] else ""}</div>
    <div class="learn" id="l-evo-interactions"></div>
  </div>
  <div class="chart-card" style="margin-top:20px">
    <h3>Piezas publicadas al mes por red <i class="info-icon" data-tip="Número de publicaciones (posts, reels y videos) hechas en cada red por mes.">i</i></h3>
    <div class="chart-wrap" style="height:320px"><canvas id="c-evo-pieces"></canvas></div>
    {foot}
    <div class="learn" id="l-evo-pieces"></div>
  </div>
  <script>
  (function () {{
    const EVO = {payload};
    const NETS = [
      {{ key: "ig", name: "Instagram", color: "#e1306c" }},
      {{ key: "fb", name: "Facebook", color: "#1877f2" }},
      {{ key: "tt", name: "TikTok", color: "#000000" }},
      {{ key: "li", name: "LinkedIn", color: "#0a66c2" }},
    ];
    const FULL = {json.dumps(full, ensure_ascii=False)};
    const f = n => n == null ? "—" : Number(n).toLocaleString("es-CO");
    const signed = n => (n > 0 ? "+" : n < 0 ? "−" : "") + Math.abs(n).toLocaleString("es-CO");
    const pct = x => (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toLocaleString("es-CO", {{ minimumFractionDigits: 1, maximumFractionDigits: 1 }}) + "%";
    const dec = x => x.toLocaleString("es-CO", {{ maximumFractionDigits: 1 }});
    const avg = a => a.length ? a.reduce((s, v) => s + v, 0) / a.length : 0;
    const setLearn = (id, html) => {{ const el = document.getElementById(id); if (el) el.innerHTML = "<p>" + html + "</p>"; }};
    const rgba = (hex, a) => {{ const n = parseInt(hex.slice(1), 16); return `rgba(${{n >> 16}},${{(n >> 8) & 255}},${{n & 255}},${{a}})`; }};

    const lastIdx = EVO.months.length - 1;
    const complete = EVO.partial ? lastIdx : lastIdx + 1;
    const labels = EVO.months.map((m, i) => (EVO.partial && i === lastIdx) ? m + "*" : m);
    const totals = src => EVO.months.map((_, i) => NETS.reduce((s, n) => s + src[n.key][i], 0));

    function stacked(id, src, unit) {{
      const el = document.getElementById(id);
      if (!el) return;
      new Chart(el, {{
        type: "bar",
        data: {{ labels, datasets: NETS.map(n => ({{
          label: n.name, data: src[n.key],
          backgroundColor: labels.map((_, i) => (EVO.partial && i === lastIdx) ? rgba(n.color, 0.35) : n.color),
          borderColor: "#ffffff", borderWidth: 1, maxBarThickness: 44,
        }})) }},
        options: {{
          responsive: true, maintainAspectRatio: false,
          interaction: {{ mode: "index", intersect: false }},
          scales: {{
            x: {{ stacked: true, grid: {{ display: false }} }},
            y: {{ stacked: true, beginAtZero: true, grid: {{ color: "#F0EDE4" }}, ticks: {{ callback: v => Number(v).toLocaleString("es-CO"), maxTicksLimit: 6 }} }},
          }},
          plugins: {{
            legend: {{ position: "top", align: "start", labels: {{ boxWidth: 10, boxHeight: 10, usePointStyle: false }} }},
            tooltip: {{ callbacks: {{
              label: c => ` ${{c.dataset.label}}: ${{f(c.raw)}}`,
              footer: items => `Total: ${{f(items.reduce((s, it) => s + it.raw, 0))}} ${{unit}}`,
            }} }},
          }},
        }},
      }});
    }}

    function followers() {{
      const box = document.getElementById("evo-multiples");
      if (!box) return;
      const stats = [];
      NETS.forEach(n => {{
        const s = EVO.followers[n.key];
        const i0 = s.findIndex(v => v != null);
        let i1 = s.length - 1; while (i1 >= 0 && s[i1] == null) i1--;
        if (i0 < 0 || i1 <= i0) return;
        const d = s[i1] - s[i0], p = d / s[i0] * 100, since = FULL[EVO.fMonths[i0]];
        stats.push({{ n, d, p, since }});
        const card = document.createElement("div");
        card.className = "evo-mini";
        card.innerHTML = `
          <div class="evo-mini-top"><i style="background:${{n.color}}"></i>${{n.name}}</div>
          <div class="evo-mini-val">${{f(s[i1])}}</div>
          <div class="evo-mini-delta ${{d >= 0 ? "up" : "down"}}">${{d >= 0 ? "▲" : "▼"}} ${{signed(d)}} (${{pct(p)}}) <span>desde ${{since}}</span></div>
          <div class="evo-mini-chart"><canvas aria-label="Seguidores de ${{n.name}} por mes"></canvas></div>`;
        box.appendChild(card);
        new Chart(card.querySelector("canvas"), {{
          type: "line",
          // Cada tarjeta arranca en su primer mes medido; la línea une solo mediciones reales.
          data: {{ labels: EVO.fMonths.slice(i0, i1 + 1), datasets: [{{
            data: s.slice(i0, i1 + 1), borderColor: n.color, borderWidth: 2, tension: 0.25, spanGaps: true,
            pointRadius: s.slice(i0, i1 + 1).map((v, i) => v == null ? 0 : (i === i1 - i0 ? 4.5 : 3.5)), pointBackgroundColor: n.color,
            pointBorderColor: "#fff", pointBorderWidth: 1.5, pointHitRadius: 12,
          }}] }},
          options: {{
            responsive: true, maintainAspectRatio: false, animation: false,
            interaction: {{ mode: "index", intersect: false }},
            plugins: {{ legend: {{ display: false }}, tooltip: {{ displayColors: false, callbacks: {{ label: c => `${{f(c.raw)}} seguidores` }} }} }},
            scales: {{ x: {{ grid: {{ display: false }}, border: {{ display: false }}, ticks: {{ font: {{ size: 10 }} }} }}, y: {{ display: false, grace: "15%" }} }},
          }},
        }});
      }});
      if (!stats.length) return;
      const best = [...stats].sort((a, b) => b.p - a.p)[0];
      let t = `<strong>${{best.n.name}}</strong> es la red que más crece: ${{signed(best.d)}} seguidores (${{pct(best.p)}}) desde ${{best.since}}.`;
      const others = stats.filter(s => s !== best && s.d > 0).map(s => `${{s.n.name}} (${{signed(s.d)}} desde ${{s.since}})`);
      if (others.length) t += ` También suman ${{others.join(" y ")}}.`;
      stats.filter(s => s.d < 0).forEach(s => {{ t += ` ${{s.n.name}} baja levemente: ${{signed(s.d)}} seguidores (${{pct(s.p)}}) desde ${{s.since}}.`; }});
      setLearn("l-evo-followers", t);
    }}

    function learnInteractions() {{
      const tot = totals(EVO.interactions).slice(0, complete);
      if (!tot.length) return;
      const peak = tot.indexOf(Math.max(...tot));
      const lead = NETS.map(n => ({{ n, v: EVO.interactions[n.key][peak] }})).sort((a, b) => b.v - a.v)[0];
      let t = `El mes con más interacciones fue <strong>${{FULL[EVO.months[peak]]}}</strong> (${{f(tot[peak])}})`;
      t += lead.v / tot[peak] >= 0.6 ? `, impulsado por ${{lead.n.name}} (${{Math.round(lead.v / tot[peak] * 100)}}% del mes).` : ".";
      if (complete >= 3) {{
        const k = complete - 3, last3 = tot.slice(k);
        const bi = k + last3.indexOf(Math.max(...last3));
        t += ` En los últimos tres meses completos, <strong>${{FULL[EVO.months[bi]]}}</strong> lidera con ${{f(tot[bi])}}`;
        t += bi !== k && tot[k] > 0 ? `, ${{dec(tot[bi] / tot[k])}} veces ${{FULL[EVO.months[k]]}}.` : ".";
      }}
      setLearn("l-evo-interactions", t);
    }}

    function learnPieces() {{
      const tot = totals(EVO.pieces).slice(0, complete);
      if (!tot.length) return;
      const peak = tot.indexOf(Math.max(...tot));
      let t = `El mes con más piezas publicadas fue <strong>${{FULL[EVO.months[peak]]}}</strong> (${{f(tot[peak])}}).`;
      if (complete >= 3) {{
        const k = complete - 3;
        t += ` En los últimos tres meses completos el ritmo pasó de ${{f(tot[k])}} piezas en ${{FULL[EVO.months[k]]}} a ${{f(tot[complete - 1])}} en ${{FULL[EVO.months[complete - 1]]}}.`;
        if (k >= 2) {{
          const drops = NETS.map(n => {{
            const before = avg(EVO.pieces[n.key].slice(0, k)), after = avg(EVO.pieces[n.key].slice(k, complete));
            return {{ n, before, after, rel: before ? (after - before) / before : 0 }};
          }}).filter(x => x.before >= 2 && x.rel <= -0.3).sort((a, b) => a.rel - b.rel);
          if (drops.length) {{
            const x = drops[0];
            t += ` ${{x.n.name}} es la red que más baja su frecuencia (${{dec(x.before)}} → ${{dec(x.after)}} piezas al mes).`;
          }}
        }}
      }}
      setLearn("l-evo-pieces", t);
    }}

    function run() {{
      followers();
      stacked("c-evo-interactions", EVO.interactions, "interacciones");
      stacked("c-evo-pieces", EVO.pieces, "piezas");
      learnInteractions();
      learnPieces();
    }}
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run); else run();
  }})();
  </script>
{END}
"""


def inject(path: Path, block: str) -> tuple[str, str]:
    src = path.read_text()
    if START in src and END in src:
        a, b = src.index(START), src.index(END) + len(END)
        return src[:a] + block.rstrip("\n") + src[b:], "actualizado"
    if ANCHOR not in src:
        raise SystemExit(f"No encontré el punto de inserción en {path}")
    return src.replace(ANCHOR, ANCHOR + block, 1), "insertado"


def main() -> int:
    data = build_data(Supabase())
    block = render_block(data)
    for t in TARGETS:
        new, action = inject(t, block)
        t.write_text(new)
        print(f"✓ {t.relative_to(ROOT)}: bloque {action}")
    print(f"  meses: {data['months'][0]}–{data['months'][-1]}  parcial={data['partial']} (hasta el {data['cutoffDay']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
