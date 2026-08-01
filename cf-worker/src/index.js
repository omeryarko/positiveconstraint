// Replicates site/.htaccess behavior on Cloudflare: force https + apex host,
// legacy path redirects, and a 404 that serves index.html content (status 404
// preserved, matching Apache's ErrorDocument default — keeps it a real 404 for SEO).
// Pretty URLs (/foo -> /foo/) and directory index resolution are handled natively
// by the "auto-trailing-slash" assets html_handling, so they don't need code here.

// Serve-signal classification: user-triggered AI fetchers ("ai-assistant") vs
// training/indexing crawlers ("ai-crawler"). Lists mirror site/robots.txt.
// Not using request.cf.botManagement — that's a paid Bot Management field, absent on Free.
const AI_ASSISTANT_UAS = ["Claude-User", "ChatGPT-User", "Perplexity-User"];
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

function ideaSlug(pathname) {
  const m = pathname.match(/^\/ideas\/([^/]+)/);
  return m ? m[1] : "";
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

    if (uaClass !== "other" && env.AI_SERVE_SIGNAL) {
      if (grabToken && uaClass === "ai-assistant") {
        const dotIdx = grabToken.indexOf(".");
        const sourceSlug = dotIdx > 0 ? grabToken.slice(0, dotIdx) : "";
        // Keep the token (after the dot) so a chain hit joins to its origin grab
        // record on `token` — yields time-to-activation, not just slug attribution.
        const token = dotIdx > 0 ? grabToken.slice(dotIdx + 1) : grabToken;
        env.AI_SERVE_SIGNAL.writeDataPoint({
          blobs: ["chain", ideaSlug(url.pathname), sourceSlug, token, ua],
          indexes: ["chain"],
        });
      }
      env.AI_SERVE_SIGNAL.writeDataPoint({
        blobs: [uaClass, ideaSlug(url.pathname), ua],
        indexes: [uaClass],
      });
    }

    if (grabToken) {
      url.searchParams.delete("g");
      request = new Request(url, request);
    }

    let response = await env.ASSETS.fetch(request);

    if (response.status === 404) {
      const indexRequest = new Request(new URL("/", url), request);
      const indexResponse = await env.ASSETS.fetch(indexRequest);
      response = new Response(indexResponse.body, {
        status: 404,
        headers: indexResponse.headers,
      });
    }

    response = new Response(response.body, response);
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("text/html")) {
      response.headers.set("Cache-Control", "public, max-age=3600");
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
