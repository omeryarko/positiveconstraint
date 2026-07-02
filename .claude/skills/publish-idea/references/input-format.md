# Input format for publish-idea

One UTF-8 markdown file: a YAML-ish front-matter block delimited by `---`, then
the article body in a lightweight markdown dialect.

## Front-matter fields

| field            | required | notes |
|------------------|----------|-------|
| `slug`           | yes      | kebab-case; becomes the URL `/ideas/<slug>/`. |
| `title`          | yes      | H1 + `<title>` + map/index/card labels. |
| `category`       | yes      | `concepts`, `services`, `work`, `about`, or `frameworks`. New values need `category_label` + `category_color`. |
| `summary`        | yes      | Italic hook under the title. Map node + index card use the first ~100 chars. Use `>` for a folded multi-line value. |
| `tags`           | no       | Inline list: `[a, b, c]`. Rendered as tag chips. |
| `read_time`      | no       | Free text, e.g. `8 min read`. |
| `category_label` | no       | Display label if it differs from `category.capitalize()`. |
| `category_color` | no       | Only for a brand-new category. Hex or `var(--color-...)`. |
| `connections`    | no       | List of `{target, label, reverse_label}` — usually filled after the approval step. |

### connections

```yaml
connections:
  - {target: abstraction, label: builds on, reverse_label: applied in}
  - {target: core-constraints, label: illustrates}   # reverse_label defaults to label
```

- `target` — slug of an existing `/ideas/<slug>/` page. Must exist.
- `label` — how the new page relates to the target (shown on the new page).
- `reverse_label` — how the target relates back (shown on the target's page).
- Labels are lowercase verb phrases, rendered verbatim; the group heading is the
  Title-Cased label and `conn-type` is the UPPERCASED label.
- Self-connections are rejected.

## Body dialect

Blocks are separated by blank lines.

| you write | becomes |
|-----------|---------|
| `## Heading` | `<h2>` |
| `### Heading` | `<h3>` |
| plain paragraph | `<p>` |
| `**bold**` / `*italic*` / `[text](url)` | inline `<strong>` / `<em>` / `<a>` |
| a `>`-prefixed block, optional `> — Author` last line | `<blockquote><p>…</p><cite>— Author</cite></blockquote> |
| `@youtube[VIDEO_ID \| title \| 16-9]` | responsive YouTube embed. Ratio `16-9` (default) or `1-1`. |
| `@image[/media/file.png \| alt text \| caption]` | `<figure class="media-figure">` with caption. Omit the caption for a plain `<img class="media-img">`. |

Raw HTML entities (e.g. `&mdash;`, `&nbsp;`) pass through untouched, so you can
match the existing pages' typography.

### Images

Reference images as `/media/<file>` and make sure the file is in `site/media/`
before staging — the script warns about any referenced media it can't find and
includes new media files in the upload manifest automatically.

## Example

```markdown
---
slug: altitude-thinking
title: Altitude Thinking
category: concepts
summary: >
  A worked example of finding the one unchanging element that reorganizes
  everything around it.
tags: [constraints, abstraction]
read_time: 8 min read
connections:
  - {target: abstraction, label: builds on, reverse_label: applied in}
---
## The One That Reorganizes Everything

Peru has many unchanging truths. Only **altitude** tied the land, the
ingredients, and the culture together.

> "Art lives from constraints and dies from freedom."
> — Leonardo da Vinci

@image[/media/altitude.png | Peru's altitude levels | Altitude as a core constraint]

### Why It Works

The mind takes the path of least resistance. A constraint blocks it.
```
