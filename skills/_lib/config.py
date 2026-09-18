"""Shared constants for the publish-idea skill family, extracted from the
original monolithic scripts/publish.py so every skill (render-og, build-page,
update-indexes, deploy-site) agrees on the same values.

Nothing here reads the filesystem or does I/O — see site_io.py for that.
"""

# ---------------------------------------------------------------- tracking

# Google Analytics 4 measurement ID baked into page-template.html's <head>.
# Informational here (the template already has it hardcoded) — kept as a
# single source of truth for anything that needs to reference or verify it.
GA_TAG = "G-N9DEMEQG7C"

# LinkedIn Insight Tag partner ID baked into page-template.html's footer
# (must stay in the footer, not <head> — see build-page/SKILL.md).
LINKEDIN_PARTNER_ID = "3001121"

# ------------------------------------------------------------------- URLs

CANONICAL_URL_PREFIX = "https://positiveconstraint.com"

# --------------------------------------------------------------- categories

# Default color per category when a page/map doesn't already define one.
# ("frameworks" and "concepts" share the site's red accent; category colors
# registered on the map/index at publish time take priority over these.)
CATEGORY_COLORS = {
    "concepts": "#FF4040",
    "frameworks": "#FF4040",
    "services": "var(--color-text-primary)",
    "work": "var(--color-text-secondary)",
    "about": "var(--color-text-tertiary)",
}

DEFAULT_CATEGORY_COLOR = "var(--color-text-secondary)"

# ----------------------------------------------------------------- sections

# A piece publishes under /<section>/<slug>/. "ideas" is the default tree;
# "braintail" is used for the Braintail brand-review series. Both currently
# resolve to the same breadcrumb link/label back to the main ideas index —
# preserved exactly as the original template did it, quirk and all.
SECTION_DEFAULTS = {
    "ideas": {"link": "/ideas/", "label": "Ideas"},
    "braintail": {"link": "/ideas/", "label": "Ideas"},
}
DEFAULT_SECTION = "ideas"

# How many related-idea cards a standalone page shows. The map/graph keeps
# every edge; the page just caps the visible cards to stay clean.
MAX_RELATED_CARDS = 4

# ------------------------------------------------------------------ sitemap

# <priority> for a new page's <url> entry in /sitemap.xml.
SITEMAP_PRIORITIES = {
    "work": "0.6",
    "_default": "0.7",
}

# Surfaces whose <lastmod> is refreshed on every publish (site sections that
# every publish rewrites in some way).
SITEMAP_ALWAYS_TOUCHED_SURFACES = [
    f"{CANONICAL_URL_PREFIX}/",
    f"{CANONICAL_URL_PREFIX}/ideas/",
    f"{CANONICAL_URL_PREFIX}/map/",
]
SITEMAP_BRAINTAIL_SURFACE = f"{CANONICAL_URL_PREFIX}/braintail/"

# -------------------------------------------------------------------- llms.txt

# Which /llms.txt section a category's bullet is filed under.
LLMS_TXT_CATEGORIES = {
    "concepts": "## Core ideas",
    "frameworks": "## Core ideas",
    "reflections": "## Core ideas",
    "services": "## Practice & work",
    "work": "## Practice & work",
    "brand-reviews": "## Braintail — Brand Reviews",
}
LLMS_TXT_DEFAULT_SECTION = "## Optional"
