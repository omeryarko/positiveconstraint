// Replicates site/.htaccess behavior on Cloudflare: force https + apex host,
// legacy path redirects, plain-text 404 with recovery links, and markdown
// content negotiation for idea pages (acceptmarkdown.com). Pretty URLs
// (/foo -> /foo/) and directory index resolution are handled natively by the
// "auto-trailing-slash" assets html_handling, so they don't need code here.

// Serve-signal classification: user-triggered AI fetchers ("ai-assistant") vs
// training/indexing crawlers ("ai-crawler"). Lists mirror site/robots.txt.
// Not using request.cf.botManagement — that's a paid Bot Management field, absent on Free.
const AI_ASSISTANT_UAS = ["Claude-User", "ChatGPT-User", "Perplexity-User", "Google-Agent"];
const AI_CRAWLER_UAS = [
  "ClaudeBot", "Claude-SearchBot", "anthropic-ai",
  "GPTBot", "OAI-SearchBot",
  "PerplexityBot",
  "Google-Extended", "Applebot-Extended",
  "CCBot", "meta-externalagent",
];

function classifyUA(ua) {
  if (AI_ASSISTANT_UAS.some((m) => ua.includes(m))) return "ai-assistant";
  if (AI_CRAWLER_UAS.some((m) => ua.includes(m))) return "ai-crawler";
  return "other";
}

function pathSlug(pathname) {
  const m = pathname.match(/^\/ideas\/([^/]+)/);
  if (m) return m[1];
  const clean = pathname.replace(/^\/|\/$/g, "");
  return clean ? "_" + clean : "_home";
}

// ---------------------------------------------------------------------------
// Markdown content negotiation (acceptmarkdown.com spec: Accept: text/markdown
// -> serve text/markdown; charset=utf-8, always advertise Vary: Accept on any
// HTML response so shared/CDN caches don't mix the two variants).
//
// The site is static HTML with no markdown source deployed to the edge, so
// idea pages are converted from their rendered HTML on request. Every idea
// page (built by the publish-idea skill) shares one template: an <article>
// of p/h2/h3/a/strong/em/blockquote/ul/ol/table/img/figure/iframe, a
// piece-summary paragraph, tag-category/tag-label spans, a canonical link,
// and a `var RELATED = [...]` JSON array of related-idea links. Extraction
// below is regex/tag-tree based (no DOMParser in Workers) and targets that
// exact shape; if the shape isn't found it falls back to serving plain HTML.
const SITE_ORIGIN = "https://positiveconstraint.com";
const IDEA_PAGE_RE = /^\/ideas\/([a-z0-9-]+)\/?$/i;
const VOID_TAGS = new Set(["br", "hr", "img", "meta", "link", "input", "source", "area", "col", "embed"]);

function decodeEntities(str) {
  return str
    .replace(/&nbsp;/g, " ")
    .replace(/&mdash;/g, "—")
    .replace(/&ndash;/g, "–")
    .replace(/&hellip;/g, "…")
    .replace(/&#(\d+);/g, (_, d) => String.fromCodePoint(parseInt(d, 10)))
    .replace(/&#x([0-9a-fA-F]+);/g, (_, h) => String.fromCodePoint(parseInt(h, 16)))
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

function resolveHref(href) {
  if (!href) return "";
  if (href.startsWith("//")) return "https:" + href;
  if (/^[a-z][a-z0-9+.-]*:/i.test(href)) return href; // absolute URL or mailto:/tel:/#-scheme
  if (href.startsWith("#")) return href;
  if (href.startsWith("/")) return SITE_ORIGIN + href;
  return SITE_ORIGIN + "/" + href;
}

// Parses q-values per RFC 9110 §12.5.1 and prefers markdown only when the
// client's Accept header ranks text/markdown at or above text/html.
function prefersMarkdown(acceptHeader) {
  if (!acceptHeader || !acceptHeader.toLowerCase().includes("markdown")) return false;
  const entries = acceptHeader.split(",").map((part) => {
    const pieces = part.trim().split(";");
    const type = (pieces.shift() || "").trim().toLowerCase();
    let q = 1;
    for (const p of pieces) {
      const m = p.trim().match(/^q=([\d.]+)$/i);
      if (m) q = parseFloat(m[1]);
    }
    return { type, q };
  });
  const matches = (type, target) => type === target || type === "text/*" || type === "*/*";
  let mdQ = -1;
  let htmlQ = -1;
  for (const e of entries) {
    if (matches(e.type, "text/markdown") && e.q > mdQ) mdQ = e.q;
    if (matches(e.type, "text/html") && e.q > htmlQ) htmlQ = e.q;
  }
  if (mdQ <= 0) return false;
  if (htmlQ < 0) return true;
  return mdQ > htmlQ;
}

function parseAttrs(attrStr) {
  const attrs = {};
  const re = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"/g;
  let m;
  while ((m = re.exec(attrStr))) attrs[m[1].toLowerCase()] = decodeEntities(m[2]);
  return attrs;
}

// Minimal streaming-free HTML-to-tree parser scoped to the tag vocabulary
// used inside idea-page <article> content. Not a general HTML parser.
function parseNodes(html) {
  const tokenRe = /<!--[\s\S]*?-->|<\/?[a-zA-Z][a-zA-Z0-9]*(?:\s+[^<>]*)?\/?>|[^<]+/g;
  const root = { tag: "#root", children: [] };
  const stack = [root];
  let match;
  while ((match = tokenRe.exec(html))) {
    const tok = match[0];
    if (tok.startsWith("<!--")) continue;
    if (tok[0] !== "<") {
      stack[stack.length - 1].children.push({ type: "text", value: decodeEntities(tok) });
      continue;
    }
    const closing = tok[1] === "/";
    const selfClosing = /\/>\s*$/.test(tok);
    const tagMatch = tok.match(/^<\/?([a-zA-Z][a-zA-Z0-9]*)/);
    if (!tagMatch) continue;
    const tag = tagMatch[1].toLowerCase();
    if (closing) {
      for (let i = stack.length - 1; i > 0; i--) {
        if (stack[i].tag === tag) {
          stack.length = i;
          break;
        }
      }
      continue;
    }
    const attrStrMatch = tok.match(/^<[a-zA-Z][a-zA-Z0-9]*([\s\S]*?)\/?>$/);
    const attrs = attrStrMatch ? parseAttrs(attrStrMatch[1]) : {};
    const node = { type: "element", tag, attrs, children: [] };
    stack[stack.length - 1].children.push(node);
    if (!VOID_TAGS.has(tag) && !selfClosing) stack.push(node);
  }
  return root.children;
}

function renderNodes(nodes) {
  return nodes.map(renderNode).join("");
}

// Like renderNodes, but drops whitespace-only text nodes first. Source HTML
// is pretty-printed with newlines/indentation between block-level siblings
// (e.g. between </p> and <p>) — those text nodes carry no content but would
// otherwise leak in as a stray leading space on the next line.
function renderBlockNodes(nodes) {
  return renderNodes(nodes.filter((n) => n.type !== "text" || n.value.trim() !== ""));
}

function collectRows(node) {
  let rows = [];
  for (const c of node.children || []) {
    if (c.type !== "element") continue;
    if (c.tag === "tr") rows.push(c);
    else rows = rows.concat(collectRows(c));
  }
  return rows;
}

function renderTable(tableNode) {
  const rows = collectRows(tableNode);
  if (!rows.length) return "";
  const lines = [];
  rows.forEach((row, idx) => {
    const cells = row.children.filter((c) => c.type === "element" && (c.tag === "td" || c.tag === "th"));
    const cellText = cells.map((c) => renderNodes(c.children).trim().replace(/\|/g, "\\|").replace(/\s*\n\s*/g, " "));
    lines.push("| " + cellText.join(" | ") + " |");
    if (idx === 0) lines.push("| " + cells.map(() => "---").join(" | ") + " |");
  });
  return lines.join("\n") + "\n\n";
}

function renderNode(node) {
  if (node.type === "text") return node.value.replace(/[ \t\r\n]+/g, " ");
  const { tag, attrs, children } = node;
  switch (tag) {
    case "p": {
      const inline = renderNodes(children).trim();
      return inline ? inline + "\n\n" : "";
    }
    case "h1":
      return "# " + renderNodes(children).trim() + "\n\n";
    case "h2":
      return "## " + renderNodes(children).trim() + "\n\n";
    case "h3":
      return "### " + renderNodes(children).trim() + "\n\n";
    case "h4":
      return "#### " + renderNodes(children).trim() + "\n\n";
    case "strong":
    case "b": {
      const t = renderNodes(children).trim();
      return t ? "**" + t + "**" : "";
    }
    case "em":
    case "i": {
      const t = renderNodes(children).trim();
      return t ? "*" + t + "*" : "";
    }
    case "a": {
      const href = resolveHref(attrs.href);
      const text = renderNodes(children).trim();
      if (!href) return text;
      return "[" + (text || href) + "](" + href + ")";
    }
    case "br":
      return "\n";
    case "hr":
      return "\n---\n\n";
    case "ul": {
      const items = children.filter((c) => c.type === "element" && c.tag === "li");
      const out = items.map((li) => "- " + renderNodes(li.children).trim().replace(/\s*\n\s*/g, " ")).join("\n");
      return out ? out + "\n\n" : "";
    }
    case "ol": {
      const items = children.filter((c) => c.type === "element" && c.tag === "li");
      const out = items
        .map((li, i) => `${i + 1}. ` + renderNodes(li.children).trim().replace(/\s*\n\s*/g, " "))
        .join("\n");
      return out ? out + "\n\n" : "";
    }
    case "li":
      return renderNodes(children);
    case "blockquote": {
      const parts = [];
      for (const c of children) {
        if (c.type === "element" && c.tag === "cite") {
          const t = renderNodes(c.children).trim();
          if (t) parts.push("— " + t);
        } else {
          const t = renderNode(c).trim();
          if (t) parts.push(t);
        }
      }
      const body = parts.join("\n");
      return body ? body.split("\n").map((l) => (l ? "> " + l : ">")).join("\n") + "\n\n" : "";
    }
    case "cite":
      return renderNodes(children);
    case "span": {
      // callout-label spans (e.g. "SEQUOIA'S DESCRIPTION") sit right before
      // a sibling <p> in the source with no separator between them — render
      // as its own bold line so it doesn't run into the paragraph that follows.
      if ((attrs.class || "").includes("callout-label")) {
        const t = renderNodes(children).trim();
        return t ? "**" + t + "**\n\n" : "";
      }
      return renderNodes(children);
    }
    case "img": {
      const src = resolveHref(attrs.src);
      const alt = attrs.alt || "";
      return src ? "![" + alt + "](" + src + ")\n\n" : "";
    }
    case "figure": {
      const imgNode = children.find((c) => c.type === "element" && c.tag === "img");
      const capNode = children.find((c) => c.type === "element" && c.tag === "figcaption");
      let out = imgNode ? renderNode(imgNode) : "";
      if (capNode) {
        const cap = renderNodes(capNode.children).trim();
        if (cap) out += "*" + cap + "*\n\n";
      }
      return out;
    }
    case "figcaption":
      return "";
    case "iframe": {
      const src = attrs.src || "";
      const title = attrs.title || "Video";
      return src ? "[" + title + "](" + src + ")\n\n" : "";
    }
    case "table":
      return renderTable(node);
    case "div": {
      if ((attrs.class || "").includes("callout")) {
        const inner = renderBlockNodes(children).trim();
        return inner ? inner.split("\n").map((l) => (l ? "> " + l : ">")).join("\n") + "\n\n" : "";
      }
      return renderBlockNodes(children);
    }
    default:
      return renderNodes(children);
  }
}

// Builds the markdown variant of an idea page from its rendered HTML.
// Returns null when the page doesn't match the expected idea-page template,
// so the caller can fall back to serving the original HTML untouched.
function extractMarkdown(html, canonicalFallback) {
  const articleMatch = html.match(/<article>([\s\S]*?)<\/article>/);
  if (!articleMatch) return null;

  const titleMatch = html.match(/<h1>([\s\S]*?)<\/h1>/);
  const title = titleMatch ? decodeEntities(titleMatch[1].replace(/<[^>]+>/g, "")).trim() : "";

  const categoryMatch = html.match(/<div class="tag-category">([^<]*)<\/div>/);
  const category = categoryMatch ? decodeEntities(categoryMatch[1]).trim() : "";

  const summaryMatch = html.match(/<p class="piece-summary">([\s\S]*?)<\/p>/);
  const summary = summaryMatch ? decodeEntities(summaryMatch[1].replace(/<[^>]+>/g, "")).trim() : "";

  const tagLabels = [...html.matchAll(/<span class="tag-label">([^<]*)<\/span>/g)].map((m) =>
    decodeEntities(m[1]).trim()
  );

  const canonicalMatch = html.match(/<link rel="canonical" href="([^"]*)"/);
  const canonical = canonicalMatch ? canonicalMatch[1] : canonicalFallback;

  const body = renderBlockNodes(parseNodes(articleMatch[1]))
    // <br/> is followed in the source by a newline + indentation before the
    // next word, which collapses to a stray leading space on the new line.
    .replace(/^[ \t]+/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (!body) return null;

  let related = [];
  const relatedMatch = html.match(/var RELATED = (\[[\s\S]*?\]);/);
  if (relatedMatch) {
    try {
      related = JSON.parse(relatedMatch[1]);
    } catch (e) {
      related = [];
    }
  }
  const seenUrls = new Set();
  related = related.filter((r) => {
    if (!r || !r.url || seenUrls.has(r.url)) return false;
    seenUrls.add(r.url);
    return true;
  });

  const parts = [];
  parts.push("# " + (title || "Untitled"));
  if (category) parts.push("_" + category + "_");
  if (summary) parts.push("> " + summary);
  if (tagLabels.length) parts.push("**Tags:** " + tagLabels.join(", "));
  parts.push(body);
  if (related.length) {
    parts.push(
      "## Related Ideas\n\n" +
        related.map((r) => "- [" + r.title + "](" + SITE_ORIGIN + r.url + ") — " + r.label).join("\n")
    );
  }
  parts.push("---\nSource: " + canonical);

  return parts.filter(Boolean).join("\n\n") + "\n";
}

const LEGACY_REDIRECTS = {
  "/about": "/ideas/about/",
  "/services": "/ideas/services/",
  "/faq": "/ideas/faq/",
  "/contact": "/ideas/contact/",
  "/abstraction": "/ideas/abstraction/",
  "/process": "/ideas/process/",
  "/core-constraints": "/ideas/core-constraints/",
  "/positive-constraint": "/ideas/positive-constraint/",
  "/work/tapouts": "/ideas/work-tapouts/",
  "/work/leap-commerce": "/ideas/work-leap-commerce/",
  "/work/user1st": "/ideas/work-user1st/",
  "/work/cortisense": "/ideas/work-cortisense/",
  "/work": "/ideas/work/",
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.protocol === "http:") {
      url.protocol = "https:";
      return Response.redirect(url.toString(), 301);
    }

    if (url.hostname === "www.positiveconstraint.com") {
      url.hostname = "positiveconstraint.com";
      return Response.redirect(url.toString(), 301);
    }

    // Grab beacon: first-party same-origin signal that a human chose to carry an
    // idea (Copy as markdown / Download .md). Fires from the page JS via
    // navigator.sendBeacon, so ad blockers (which kill gtag) don't touch it.
    // Unlike Serve/Chain, grab is a *human* signal — write it regardless of UA
    // class (uaClass is "other" for a normal browser). Log no IP/UA (human PII);
    // drop known crawlers to keep scraper noise out.
    if (url.pathname === "/grab" && request.method === "POST") {
      const beaconUA = request.headers.get("User-Agent") || "";
      if (env.AI_SERVE_SIGNAL && classifyUA(beaconUA) !== "ai-crawler") {
        let slug = "";
        let token = "";
        let action = "";
        try {
          const body = await request.json();
          slug = String(body.slug || "");
          token = String(body.token || "");
          action = String(body.action || "");
        } catch (e) {}
        env.AI_SERVE_SIGNAL.writeDataPoint({
          blobs: ["grab", slug, token, action],
          indexes: ["grab"],
        });
      }
      return new Response(null, { status: 204 });
    }

    const path = url.pathname.replace(/\/$/, "") || "/";
    const legacyTarget = LEGACY_REDIRECTS[path];
    if (legacyTarget) {
      url.pathname = legacyTarget;
      return Response.redirect(url.toString(), 301);
    }

    const ua = request.headers.get("User-Agent") || "";
    const uaClass = classifyUA(ua);
    const grabToken = url.searchParams.get("g");
    const ref = url.searchParams.get("ref") || "";

    if (grabToken || ref) {
      url.searchParams.delete("g");
      url.searchParams.delete("ref");
      request = new Request(url, request);
    }

    let response = await env.ASSETS.fetch(request);

    // Only log AI hits for paths that resolve to real content — skip 404s,
    // which are overwhelmingly vulnerability scanners spoofing AI UA strings.
    if (uaClass !== "other" && env.AI_SERVE_SIGNAL && response.status !== 404) {
      if (grabToken && uaClass === "ai-assistant") {
        const dotIdx = grabToken.indexOf(".");
        const sourceSlug = dotIdx > 0 ? grabToken.slice(0, dotIdx) : "";
        const token = dotIdx > 0 ? grabToken.slice(dotIdx + 1) : grabToken;
        env.AI_SERVE_SIGNAL.writeDataPoint({
          blobs: ["chain", pathSlug(url.pathname), sourceSlug, token, ua],
          indexes: ["chain"],
        });
      }
      env.AI_SERVE_SIGNAL.writeDataPoint({
        blobs: [uaClass, pathSlug(url.pathname), ua, ref],
        indexes: [uaClass],
      });
    }

    if (response.status === 404) {
      const body = [
        "Positive Constraint",
        "",
        "The requested path does not exist.",
        "",
        "Recovery starting points:",
        "  /llms.txt  - AI-oriented index of all ideas",
        "  /ideas/    - browse all ideas",
        "  /map/      - interactive knowledge map",
        "  /          - homepage",
      ].join("\n");
      response = new Response(body, {
        status: 404,
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      });
    }

    response = new Response(response.body, response);
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("text/html")) {
      response.headers.set("Cache-Control", "public, max-age=3600");
      // Any HTML response can, in principle, also be served as markdown for
      // this path in a future request — advertise that so shared caches
      // (CDN, browser) keep the two variants separate instead of serving a
      // cached markdown body to a browser or vice versa.
      response.headers.set("Vary", "Accept");

      if (
        response.status === 200 &&
        request.method === "GET" &&
        IDEA_PAGE_RE.test(url.pathname) &&
        prefersMarkdown(request.headers.get("Accept"))
      ) {
        const html = await response.text();
        const markdown = extractMarkdown(html, url.origin + url.pathname);
        if (markdown) {
          return new Response(markdown, {
            status: 200,
            headers: {
              "Content-Type": "text/markdown; charset=utf-8",
              "Cache-Control": "public, max-age=3600",
              Vary: "Accept",
            },
          });
        }
        // Template didn't match (extractMarkdown returned null) — fall back
        // to serving the HTML we already buffered into `html`.
        response = new Response(html, response);
        response.headers.set("Content-Type", contentType);
        response.headers.set("Cache-Control", "public, max-age=3600");
        response.headers.set("Vary", "Accept");
      }
    } else if (
      contentType.includes("text/css") ||
      contentType.includes("javascript") ||
      contentType.includes("image/svg+xml") ||
      contentType.includes("image/") ||
      contentType.includes("font/")
    ) {
      response.headers.set("Cache-Control", "public, max-age=2592000");
    }

    return response;
  },
};
