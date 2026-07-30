#!/usr/bin/env bash
# Migration verification harness for positiveconstraint.com.
# No dependencies beyond dig + curl. Safe to run at any time — read-only.
#
#   ./verify.sh snapshot                  Capture current authoritative DNS as the baseline.
#   ./verify.sh compare <nameserver>      Diff a nameserver's answers against the baseline.
#                                         Run this against Cloudflare's assigned NS while
#                                         Namecheap is STILL authoritative — the critical gate.
#   ./verify.sh worker <base-url>         HTTP smoke test (redirects, 404 status, caching).
#
# Typical cutover sequence:
#   ./verify.sh snapshot                                   # before touching anything
#   ./verify.sh worker https://positiveconstraint.omer-2c2.workers.dev
#   ...recreate records in Cloudflare...
#   ./verify.sh compare kate.ns.cloudflare.com             # MUST pass before flipping NS
#   ...flip nameservers, attach apex + www custom domains...
#   ./verify.sh compare kate.ns.cloudflare.com
#   ./verify.sh worker https://positiveconstraint.com

set -uo pipefail

# Both positiveconstraint.com and braintail.ai live on the same Namecheap plan
# (same web IP), so both need checking. Override with: DOMAIN=braintail.ai ./verify.sh ...
DOMAIN=${DOMAIN:-positiveconstraint.com}
BASELINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/dns-baseline.${DOMAIN}.txt"
pass=0; fail=0; warn=0

ok()   { printf '  \033[32mPASS\033[0m  %s\n' "$1"; pass=$((pass+1)); }
no()   { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; fail=$((fail+1)); }
note() { printf '  \033[33mWARN\033[0m  %s\n' "$1"; warn=$((warn+1)); }
head_() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# dig wrapper: optional @nameserver, normalised output (sorted, TXT chunks joined).
q() { # q <type> <name> [nameserver]
  local t=$1 n=$2 ns=${3:-}
  local out
  if [[ -n $ns ]]; then out=$(dig +short "@$ns" "$t" "$n" 2>/dev/null)
  else out=$(dig +short "$t" "$n" 2>/dev/null); fi
  # Join adjacent quoted TXT chunks ("aaa" "bbb" -> aaabbb) and strip quotes.
  printf '%s\n' "$out" | sed -e 's/" "//g' -e 's/"//g' | sed '/^$/d' | LC_ALL=C sort
}

# Records that must survive the move. Mail and Search Console depend on these.
capture() { # capture [nameserver]
  local ns=${1:-}
  { echo "# DNS baseline for $DOMAIN"
    echo "# captured $(date -u +%Y-%m-%dT%H:%M:%SZ) ${ns:+via $ns}"
    # Sweep known DKIM selectors: cPanel uses "default", Google Workspace uses
    # "google", Brevo uses "brevo1"/"brevo2" (CNAMEs). Capture whatever exists.
    local specs=("MX $DOMAIN" "TXT $DOMAIN" "TXT _dmarc.$DOMAIN" "CAA $DOMAIN")
    for sel in default google mail brevo1 brevo2; do
      specs+=("TXT ${sel}._domainkey.$DOMAIN" "CNAME ${sel}._domainkey.$DOMAIN")
    done
    for spec in "${specs[@]}"; do
      set -- $spec
      while IFS= read -r line; do
        [[ -n $line ]] && echo "$1 $2 $line"
      done < <(q "$1" "$2" "$ns")
    done
  } | LC_ALL=C sort
}

case ${1:-} in
snapshot)
  head_ "Capturing authoritative DNS baseline for $DOMAIN"
  echo "  current nameservers: $(dig +short NS "$DOMAIN" | tr '\n' ' ')"
  capture > "$BASELINE"
  echo "  wrote $(grep -vc '^#' "$BASELINE") mail/verification records to:"
  echo "  $BASELINE"
  head_ "Namecheap cPanel artifacts (drop at cutover once mail question is settled)"
  for s in mail webmail cpanel autodiscover ftp; do
    v=$(dig +short "$s.$DOMAIN" | tr '\n' ' ')
    [[ -n $v ]] && printf '  %-14s %s\n' "$s" "$v"
  done
  echo
  echo "Commit this file so the cutover session diffs against the same baseline."
  ;;

compare)
  ns=${2:-}
  [[ -z $ns ]] && { echo "usage: $0 compare <nameserver>"; exit 2; }
  [[ -f $BASELINE ]] || { echo "No baseline. Run '$0 snapshot' first."; exit 2; }

  head_ "Comparing $ns against baseline"
  live=$(capture "$ns")
  if [[ -z $(grep -v '^#' <<<"$live") ]]; then
    no "$ns returned no records for $DOMAIN — is the zone added and are you querying the right NS?"
  else
    d=$(diff <(grep -v '^#' "$BASELINE") <(grep -v '^#' <<<"$live"))
    if [[ -z $d ]]; then
      ok "all mail + verification records match the baseline exactly"
    else
      no "records differ from baseline:"
      sed 's/^/        /' <<<"$d"
    fi
  fi

  head_ "Load-bearing checks (independent of the diff)"
  # Mail is Google Workspace on both domains. positiveconstraint.com uses the
  # classic 5-record aspmx set; braintail.ai uses the single smtp.google.com record.
  mx=$(q MX "$DOMAIN" "$ns")
  base_mx=$(grep "^MX " "$BASELINE" | cut -d' ' -f3-)
  if [[ -z $mx ]]; then
    no "NO MX records — inbound mail will bounce"
  elif [[ $mx == "$base_mx" ]]; then
    n=$(grep -c . <<<"$mx")
    if [[ $(grep -civ 'google.com\.$' <<<"$mx") -eq 0 ]]; then
      ok "$n MX record(s), all Google Workspace, matching baseline"
    else
      note "$n MX record(s) match baseline but not all point at Google:
        $(tr '\n' ' ' <<<"$mx")"
    fi
  else
    no "MX records differ from baseline — inbound mail is at risk
        baseline: $(tr '\n' ' ' <<<"$base_mx")
        live:     $(tr '\n' ' ' <<<"$mx")"
  fi

  # DKIM: compare whatever selectors the baseline captured. NOTE on
  # positiveconstraint.com the only selector present is "default", which is
  # cPanel's auto-generated key, not Google Workspace's (that would be
  # "google._domainkey" and does not exist). It signs nothing — no mail leaves
  # the web host. Preserved for parity, not because it is load-bearing.
  dkim_lines=$(grep '_domainkey' "$BASELINE" || true)
  if [[ -z $dkim_lines ]]; then
    note "no DKIM selectors in baseline — nothing to compare"
  else
    dkim_bad=0
    while IFS= read -r line; do
      t=$(cut -d' ' -f1 <<<"$line"); n=$(cut -d' ' -f2 <<<"$line")
      want=$(cut -d' ' -f3- <<<"$line")
      got=$(q "$t" "$n" "$ns")
      if [[ $got != "$want" ]]; then
        no "DKIM $t $n does not match baseline
        (classic symptom: the two quoted chunks of a >255-char TXT were pasted
        with the internal quote-space-quote left in. Mail still delivers,
        DKIM silently fails.)"
        dkim_bad=1
      fi
    done <<<"$dkim_lines"
    [[ $dkim_bad -eq 0 ]] && ok "all $(grep -c . <<<"$dkim_lines") DKIM record(s) match baseline byte-for-byte"
  fi

  q TXT "google._domainkey.$DOMAIN" "$ns" | grep -q 'v=DKIM1' \
    || note "no google._domainkey record — Google Workspace DKIM signing is not
        configured for this domain. Pre-existing, not caused by the migration;
        mail currently authenticates on SPF alone. Worth fixing while in DNS."

  grep -q 'google-site-verification' <<<"$(q TXT "$DOMAIN" "$ns")" \
    && ok "google-site-verification TXT present (Search Console sc-domain property)" \
    || no "google-site-verification TXT missing — breaks DNS-verified Search Console access"

  grep -q 'v=DMARC1' <<<"$(q TXT "_dmarc.$DOMAIN" "$ns")" \
    && ok "DMARC record present" || no "DMARC record missing"

  spf=$(q TXT "$DOMAIN" "$ns" | grep '^v=spf1' || true)
  if [[ -z $spf ]]; then
    no "no SPF record — outbound mail will be treated as unauthenticated"
  else
    grep -q '_spf.google.com' <<<"$spf" \
      && ok "SPF includes _spf.google.com" \
      || no "SPF is missing _spf.google.com — Google Workspace mail will fail SPF"
    for m in '+a' 'ip4:198.177.120.13' 'spf.web-hosting.com'; do
      grep -qF -- "$m" <<<"$spf" && note "SPF still carries Namecheap-era '$m' (expected before
        the cleanup step; must be gone after. '+a' post-migration authorises
        Cloudflare's shared proxy range as senders for this domain)"
    done
  fi

  head_ "Nameserver delegation (informational)"
  echo "  authoritative now: $(dig +short NS "$DOMAIN" | tr '\n' ' ')"
  ;;

worker)
  base=${2:-}
  [[ -z $base ]] && { echo "usage: $0 worker <base-url>"; exit 2; }
  base=${base%/}

  code() { curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$1" 2>/dev/null; }
  loc()  { curl -sS -o /dev/null -w '%{redirect_url}' --max-time 20 "$1" 2>/dev/null; }
  hdr()  { curl -sSI --max-time 20 "$1" 2>/dev/null | tr -d '\r'; }

  head_ "Legacy 301 redirects → /ideas/* tree"
  for pair in \
    "/about:/ideas/about/"                     "/services:/ideas/services/" \
    "/faq:/ideas/faq/"                         "/contact:/ideas/contact/" \
    "/abstraction:/ideas/abstraction/"         "/process:/ideas/process/" \
    "/core-constraints:/ideas/core-constraints/" \
    "/positive-constraint:/ideas/positive-constraint/" \
    "/work/tapouts:/ideas/work-tapouts/"       "/work/leap-commerce:/ideas/work-leap-commerce/" \
    "/work/user1st:/ideas/work-user1st/"       "/work/cortisense:/ideas/work-cortisense/" \
    "/work:/ideas/work/"; do
    src=${pair%%:*}; want=${pair##*:}
    c=$(code "$base$src"); l=$(loc "$base$src")
    if [[ $c == 301 && $l == *"$want" ]]; then ok "$src → $want"
    else no "$src expected 301→$want, got $c → ${l:-<none>}"; fi
  done

  head_ "Pages and static assets"
  for p in / /ideas/ /ideas/core-constraints/ /map/ /robots.txt /sitemap.xml /llms.txt; do
    c=$(code "$base$p")
    [[ $c == 200 ]] && ok "$p → 200" || no "$p expected 200, got $c"
  done

  head_ "404 handling (must be a REAL 404, not a soft-404)"
  c=$(code "$base/definitely-not-a-real-page-xyz")
  [[ $c == 404 ]] && ok "unknown path returns 404 status" \
                  || no "unknown path returned $c — soft-404 is an SEO regression"

  head_ "Trailing-slash normalisation"
  c=$(code "$base/ideas/about"); l=$(loc "$base/ideas/about")
  [[ $c =~ ^30 && $l == *"/ideas/about/" ]] && ok "/ideas/about → /ideas/about/ ($c)" \
    || no "/ideas/about expected redirect to /ideas/about/, got $c → ${l:-<none>}"

  head_ "Caching"
  h=$(hdr "$base/ideas/core-constraints/")
  grep -qi 'cache-control: public, max-age=3600' <<<"$h" \
    && ok "HTML: max-age=3600" \
    || no "HTML cache-control: $(grep -i '^cache-control' <<<"$h" || echo '<none>')"
  h=$(hdr "$base/media/og/core-constraints.png")
  cc=$(grep -i '^cache-control' <<<"$h" || echo '<none>')
  if grep -qi 'max-age=0' <<<"$cc"; then
    note "OG image: $cc
        Known gap — header logic covers css/js/svg only. These are exactly what
        social + AI link-preview fetchers pull. Add png/jpg/ico to long-cache."
  else
    ok "OG image: $cc"
  fi

  # Only meaningful once the real domain is attached; workers.dev 403s a forged Host.
  if [[ $base == *positiveconstraint.com* ]]; then
    head_ "Canonical host (real domain only)"
    c=$(code "https://www.$DOMAIN/"); l=$(loc "https://www.$DOMAIN/")
    [[ $c == 301 && $l == "https://$DOMAIN/" ]] \
      && ok "www → apex 301" \
      || no "www → apex expected 301→https://$DOMAIN/, got $c → ${l:-<none>}
        If this is a connection failure, 'www' was NOT attached as its own Worker
        custom domain — the redirect in src/index.js never runs."
    c=$(code "http://$DOMAIN/")
    [[ $c =~ ^30 ]] && ok "http → https ($c)" || no "http → https expected 3xx, got $c"
  fi
  ;;

*)
  sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 2
  ;;
esac

head_ "$pass passed, $fail failed, $warn warnings"
[[ $fail -eq 0 ]] || exit 1
