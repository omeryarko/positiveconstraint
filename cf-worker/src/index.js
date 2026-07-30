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

    const path = url.pathname.replace(/\/$/, "") || "/";
    const legacyTarget = LEGACY_REDIRECTS[path];
    if (legacyTarget) {
      url.pathname = legacyTarget;
      return Response.redirect(url.toString(), 301);
    }

    // Log the Serve/Crawl signal only for requests we actually serve (not the
    // redirect hops above), so each AI fetch of a canonical /ideas/<slug>/ URL
    // is counted once. An AI UA that hits a legacy/http URL and doesn't follow
    // the 301 is intentionally not logged (accepted tradeoff — real fetchers follow).
    const ua = request.headers.get("User-Agent") || "";
    const uaClass = classifyUA(ua);
    if (uaClass !== "other" && env.AI_SERVE_SIGNAL) {
      env.AI_SERVE_SIGNAL.writeDataPoint({
        blobs: [uaClass, ideaSlug(url.pathname), ua],
        indexes: [uaClass],
      });
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
      contentType.includes("image/svg+xml")
    ) {
      response.headers.set("Cache-Control", "public, max-age=2592000");
    }

    return response;
  },
};
