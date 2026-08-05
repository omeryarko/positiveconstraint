// Read-only dashboard for the idea-usage signal ladder (Grab/Serve/Chain/Crawl).
// Separate Worker, own subdomain (dashboard.positiveconstraint.com), so the AE
// read token + Basic Auth password never touch the public site Worker
// (cf-worker/, which stays write-only: no read token, no auth surface).
//
// Data path: the AE SQL API needs a bearer token, so there's no pure
// client-side page -- this Worker queries AE server-side (AE_READ_TOKEN) and
// returns JSON; the static HTML below only renders what it's given.

const DATASET = "ai_serve_signal";

// Synthetic/test rows to keep out of every query. `status-check`/`statuscheck`
// are permanent test-beacon slugs (never real content, exclude at any date).
// The other two exclusions are narrow, dated windows for known pre-launch
// verification hits (see memory: project-dashboard, serve-signal-measurement)
// -- core-constraints and process are real ideas, so only their 2026-07-30..08-01
// rows of the specific test classes are cut, not the slugs entirely.
// AE's SQL dialect won't auto-coerce a string literal against a DateTime
// column (BETWEEN/>=/< all reject it) -- toDateTime() casts explicitly.
const TEST_WINDOW_START = "toDateTime('2026-07-30 00:00:00')";
const TEST_WINDOW_END = "toDateTime('2026-08-02 00:00:00')"; // exclusive upper bound

const EXCLUDE_SQL = `
    blob2 NOT IN ('status-check', 'statuscheck')
    AND NOT (
      (blob2 = 'core-constraints' AND blob1 = 'grab' AND timestamp >= ${TEST_WINDOW_START} AND timestamp < ${TEST_WINDOW_END})
      OR (blob2 = 'process' AND blob1 IN ('chain', 'ai-assistant') AND timestamp >= ${TEST_WINDOW_START} AND timestamp < ${TEST_WINDOW_END})
    )
`.trim();

function mainQuery(days) {
  return `
SELECT
  toDate(timestamp) AS day,
  blob1 AS class,
  blob2 AS idea_slug,
  blob4 AS ref,
  count() AS hits
FROM ${DATASET}
WHERE timestamp > NOW() - INTERVAL '${days}' DAY
  AND ${EXCLUDE_SQL}
GROUP BY day, class, idea_slug, ref
ORDER BY day DESC, hits DESC
`.trim();
}

function chainQuery(days) {
  return `
SELECT
  blob3 AS source_slug,
  blob2 AS target_slug,
  count() AS hits
FROM ${DATASET}
WHERE blob1 = 'chain'
  AND timestamp > NOW() - INTERVAL '${days}' DAY
  AND blob3 NOT IN ('status-check', 'statuscheck')
  AND ${EXCLUDE_SQL}
GROUP BY source_slug, target_slug
ORDER BY hits DESC
`.trim();
}

async function runSql(env, sql) {
  const url = `https://api.cloudflare.com/client/v4/accounts/${env.CLOUDFLARE_ACCOUNT_ID}/analytics_engine/sql`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${env.AE_READ_TOKEN}` },
    body: sql,
  });
  const body = await resp.json();
  if (!resp.ok || !body.data) {
    throw new Error(`AE SQL error (${resp.status}): ${JSON.stringify(body).slice(0, 500)}`);
  }
  return body.data;
}

function emptyCounts() {
  return { grab: 0, "ai-assistant": 0, chain: 0, "ai-crawler": 0, "ref-llms": 0 };
}

function aggregate(rows) {
  const byIdea = {};
  const daily = {}; // day -> class -> hits
  for (const r of rows) {
    const slug = r.idea_slug || "(no slug)";
    if (!byIdea[slug]) byIdea[slug] = emptyCounts();
    const cls = r.class;
    const hits = Number(r.hits);
    byIdea[slug][cls] = (byIdea[slug][cls] || 0) + hits;
    if (r.ref === "llms") byIdea[slug]["ref-llms"] += hits;

    if (!daily[r.day]) daily[r.day] = {};
    daily[r.day][cls] = (daily[r.day][cls] || 0) + hits;
  }
  return { byIdea, daily };
}

function buildResponsePayload(mainRows, chainRows, days) {
  const { byIdea, daily } = aggregate(mainRows);

  const ideas = Object.entries(byIdea)
    .map(([slug, c]) => ({
      slug,
      grabbed: c.grab,
      served: c["ai-assistant"],
      chained: c.chain,
      crawled: c["ai-crawler"],
      refLlms: c["ref-llms"],
    }))
    .sort((a, b) => b.grabbed - a.grabbed || b.served - a.served);

  const chains = chainRows.map((r) => ({
    source: r.source_slug || "(unknown)",
    target: r.target_slug || "(no slug)",
    hits: Number(r.hits),
  }));

  const chainsBySource = {};
  for (const c of chains) {
    chainsBySource[c.source] = (chainsBySource[c.source] || 0) + c.hits;
  }

  const activation = Object.entries(byIdea)
    .filter(([, c]) => c.grab > 0)
    .map(([slug, c]) => {
      const grabs = c.grab;
      const chainedHits = chainsBySource[slug] || 0;
      return {
        slug,
        grabbed: grabs,
        chained: chainedHits,
        rate: grabs ? chainedHits / grabs : 0,
      };
    })
    .sort((a, b) => b.grabbed - a.grabbed);

  const days_list = Object.keys(daily).sort();
  const series = days_list.map((day) => ({
    day,
    grabbed: daily[day].grab || 0,
    served: daily[day]["ai-assistant"] || 0,
    chained: daily[day].chain || 0,
    crawled: daily[day]["ai-crawler"] || 0,
  }));

  const totals = ideas.reduce(
    (acc, i) => {
      acc.grabbed += i.grabbed;
      acc.served += i.served;
      acc.chained += i.chained;
      acc.crawled += i.crawled;
      return acc;
    },
    { grabbed: 0, served: 0, chained: 0, crawled: 0 }
  );

  return { days, generatedAt: new Date().toISOString(), totals, ideas, chains, activation, series };
}

async function handleSignals(url, env) {
  let days = parseInt(url.searchParams.get("days") || "30", 10);
  if (!Number.isFinite(days) || days < 1) days = 30;
  if (days > 90) days = 90;

  try {
    const [mainRows, chainRows] = await Promise.all([
      runSql(env, mainQuery(days)),
      runSql(env, chainQuery(days)),
    ]);
    const payload = buildResponsePayload(mainRows, chainRows, days);
    return new Response(JSON.stringify(payload), {
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err.message || err) }), {
      status: 502,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  }
}

function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i++) result |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return result === 0;
}

function checkAuth(request, env) {
  const header = request.headers.get("Authorization") || "";
  if (!header.startsWith("Basic ")) return false;
  let decoded;
  try {
    decoded = atob(header.slice(6));
  } catch (e) {
    return false;
  }
  const idx = decoded.indexOf(":");
  const user = idx >= 0 ? decoded.slice(0, idx) : decoded;
  const pass = idx >= 0 ? decoded.slice(idx + 1) : "";
  const expectedUser = env.DASHBOARD_USER || "admin";
  if (!env.DASHBOARD_PASSWORD) return false;
  return timingSafeEqual(user, expectedUser) && timingSafeEqual(pass, env.DASHBOARD_PASSWORD);
}

function unauthorized() {
  return new Response("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="dashboard"', "content-type": "text/plain" },
  });
}

const DASHBOARD_HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Signals — positiveconstraint.com</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #ffffff; --fg: #1a1a1a; --muted: #666; --border: #ddd; --accent: #2563eb;
    --grab: #7c3aed; --serve: #2563eb; --chain: #059669; --crawl: #d97706;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #14161a; --fg: #e6e6e6; --muted: #9aa0a6; --border: #2c2f36; }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 2rem 1.5rem 4rem; background: var(--bg); color: var(--fg);
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: 14px; max-width: 1000px; margin-inline: auto;
  }
  h1 { font-size: 1.1rem; margin: 0 0 0.25rem; }
  .sub { color: var(--muted); font-size: 0.8rem; margin-bottom: 1.5rem; }
  .controls { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; }
  select, button {
    font: inherit; background: var(--bg); color: var(--fg); border: 1px solid var(--border);
    border-radius: 6px; padding: 0.35rem 0.6rem; cursor: pointer;
  }
  section { margin-bottom: 2.5rem; }
  h2 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); margin: 0 0 0.75rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th, td { text-align: right; padding: 0.35rem 0.5rem; border-bottom: 1px solid var(--border); white-space: nowrap; }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--muted); font-weight: 500; }
  tbody tr:hover { background: color-mix(in srgb, var(--fg) 5%, transparent); }
  .totals { display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
  .tile { border: 1px solid var(--border); border-radius: 8px; padding: 0.6rem 1rem; min-width: 100px; }
  .tile .n { font-size: 1.4rem; font-weight: 600; }
  .tile .l { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.03em; }
  .legend { display: flex; gap: 1rem; font-size: 0.75rem; color: var(--muted); margin-bottom: 0.5rem; }
  .legend span { display: inline-flex; align-items: center; gap: 0.3rem; }
  .swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
  .empty { color: var(--muted); font-style: italic; padding: 0.5rem 0; }
  .err { color: #dc2626; }
  svg text { fill: var(--muted); font-size: 10px; }
</style>
</head>
<body>
  <h1>Idea-usage signals</h1>
  <div class="sub" id="meta">loading…</div>

  <div class="controls">
    <label for="days">Window:</label>
    <select id="days">
      <option value="7">7 days</option>
      <option value="30" selected>30 days</option>
      <option value="90">90 days</option>
    </select>
    <button id="refresh">Refresh</button>
  </div>

  <div id="app">loading…</div>

<script>
const daysSel = document.getElementById("days");
const app = document.getElementById("app");
const meta = document.getElementById("meta");
const CLASS_COLOR = { grabbed: "var(--grab)", served: "var(--serve)", chained: "var(--chain)", crawled: "var(--crawl)" };

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtPct(x) { return (x * 100).toFixed(0) + "%"; }

function renderTotals(t) {
  return \`<div class="totals">
    \${["grabbed","served","chained","crawled"].map(k =>
      \`<div class="tile"><div class="n" style="color:\${CLASS_COLOR[k]}">\${t[k]}</div><div class="l">\${k}</div></div>\`
    ).join("")}
  </div>\`;
}

function renderIdeaTable(ideas) {
  if (!ideas.length) return '<div class="empty">No data in this window.</div>';
  const rows = ideas.map(i => \`
    <tr>
      <td>\${esc(i.slug)}</td>
      <td>\${i.grabbed}</td>
      <td>\${i.served}</td>
      <td>\${i.chained}</td>
      <td>\${i.crawled}</td>
      <td>\${i.grabbed ? fmtPct(i.chained / i.grabbed) : "–"}</td>
    </tr>\`).join("");
  return \`<table>
    <thead><tr><th>Idea</th><th>Grabbed</th><th>Served</th><th>Chained</th><th>Crawled</th><th>Activation</th></tr></thead>
    <tbody>\${rows}</tbody>
  </table>\`;
}

function renderChainTable(chains) {
  if (!chains.length) return '<div class="empty">No chain hits in this window.</div>';
  const rows = chains.map(c => \`
    <tr><td>\${esc(c.source)}</td><td>\${esc(c.target)}</td><td>\${c.hits}</td></tr>
  \`).join("");
  return \`<table>
    <thead><tr><th>Source (grabbed)</th><th>Target (fetched)</th><th>Hits</th></tr></thead>
    <tbody>\${rows}</tbody>
  </table>\`;
}

function renderActivationTable(activation) {
  if (!activation.length) return '<div class="empty">No grabs in this window.</div>';
  const rows = activation.map(a => \`
    <tr><td>\${esc(a.slug)}</td><td>\${a.grabbed}</td><td>\${a.chained}</td><td>\${fmtPct(a.rate)}</td></tr>
  \`).join("");
  return \`<table>
    <thead><tr><th>Idea</th><th>Grabbed</th><th>Chains</th><th>Rate</th></tr></thead>
    <tbody>\${rows}</tbody>
  </table>\`;
}

function renderSeriesChart(series) {
  if (!series.length) return '<div class="empty">No daily data in this window.</div>';
  const W = 900, H = 200, padL = 30, padB = 20, padT = 10, padR = 10;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const keys = ["grabbed", "served", "chained", "crawled"];
  const maxY = Math.max(1, ...series.flatMap(d => keys.map(k => d[k])));
  const n = series.length;
  const x = (i) => padL + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v) => padT + innerH - (v / maxY) * innerH;

  const paths = keys.map(k => {
    const d = series.map((row, i) => \`\${i === 0 ? "M" : "L"}\${x(i).toFixed(1)},\${y(row[k]).toFixed(1)}\`).join(" ");
    return \`<path d="\${d}" fill="none" stroke="\${CLASS_COLOR[k]}" stroke-width="2" />\`;
  }).join("");

  const step = Math.max(1, Math.ceil(n / 8));
  const labels = series.map((row, i) =>
    i % step === 0 ? \`<text x="\${x(i).toFixed(1)}" y="\${H - 4}" text-anchor="middle">\${row.day.slice(5)}</text>\` : ""
  ).join("");

  const gridY = [0, 0.5, 1].map(f => {
    const val = Math.round(maxY * f);
    return \`<line x1="\${padL}" y1="\${y(val).toFixed(1)}" x2="\${W - padR}" y2="\${y(val).toFixed(1)}" stroke="var(--border)" stroke-width="1" />
      <text x="\${padL - 4}" y="\${y(val).toFixed(1) - -3}" text-anchor="end">\${val}</text>\`;
  }).join("");

  return \`
    <div class="legend">
      \${keys.map(k => \`<span><span class="swatch" style="background:\${CLASS_COLOR[k]}"></span>\${k}</span>\`).join("")}
    </div>
    <svg viewBox="0 0 \${W} \${H}" style="width:100%; height:auto;">
      \${gridY}
      \${paths}
      \${labels}
    </svg>\`;
}

async function load() {
  const days = daysSel.value;
  meta.textContent = "loading…";
  app.textContent = "";
  try {
    const resp = await fetch("/api/signals?days=" + encodeURIComponent(days));
    const data = await resp.json();
    if (!resp.ok || data.error) throw new Error(data.error || ("HTTP " + resp.status));

    meta.textContent = "Last " + data.days + " days — generated " + new Date(data.generatedAt).toLocaleString();

    app.innerHTML = \`
      \${renderTotals(data.totals)}
      <section>
        <h2>Per-day trend</h2>
        \${renderSeriesChart(data.series)}
      </section>
      <section>
        <h2>Per idea</h2>
        \${renderIdeaTable(data.ideas)}
      </section>
      <section>
        <h2>Chain detail (grabbed → fetched)</h2>
        \${renderChainTable(data.chains)}
      </section>
      <section>
        <h2>Activation (grabbed → reached an AI via a chain link)</h2>
        \${renderActivationTable(data.activation)}
      </section>
    \`;
  } catch (err) {
    meta.textContent = "";
    app.innerHTML = '<div class="err">Failed to load: ' + esc(err.message || err) + '</div>';
  }
}

daysSel.addEventListener("change", load);
document.getElementById("refresh").addEventListener("click", load);
load();
</script>
</body>
</html>
`;

export default {
  async fetch(request, env) {
    if (!checkAuth(request, env)) return unauthorized();

    const url = new URL(request.url);
    if (url.pathname === "/api/signals") {
      return handleSignals(url, env);
    }

    return new Response(DASHBOARD_HTML, {
      headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
    });
  },
};
