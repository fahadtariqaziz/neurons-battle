"""Pure-Python helpers for URLs: normalize for de-duplication, guess the source type.

The source type here is a cheap first guess from the domain. Being "official" does NOT
make a source reliable for a claim; that is the Evidence Checker's job later.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ai_decision_arena.schemas import SourceType

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid", "gclid"}

COMMUNITY_DOMAINS = (
    "reddit.com", "news.ycombinator.com", "stackoverflow.com", "stackexchange.com",
    "serverfault.com", "superuser.com", "discord.com", "community.", "forum.", "discuss.",
)
COMMUNITY_PATHS = ("/forums/", "/forum/", "/community/", "/answers/", "/discussions/", "/questions/")
# Preferred for community_experience searches (putting "reddit" in the query text doesn't filter).
COMMUNITY_SEARCH_DOMAINS = ["reddit.com", "news.ycombinator.com", "github.com"]
OFFICIAL_DOC_HINTS = (
    "docs.", "documentation", "/docs/", "/doc/", "readthedocs.io", "learn.microsoft.com",
    "developer.", "/manual/", "/reference/", "/guide/", "/pricing",
)
BENCHMARK_HINTS = ("benchmark", "release-notes", "releasenotes", "/releases/", "changelog", "/spec")


def normalize_url(url: str) -> str:
    """Same page, same key: lowercase host, drop fragment, tracking params, trailing slash."""
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in TRACKING_PARAMS])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower().removeprefix("www."), path, query, ""))


def classify_source(url: str) -> SourceType:
    parts = urlsplit(url.lower())
    host, path = parts.netloc.removeprefix("www."), parts.path
    full = host + path
    if host == "github.com" or host.endswith(".github.com"):
        return "github"
    if any(d in host for d in COMMUNITY_DOMAINS) or any(p in path for p in COMMUNITY_PATHS):
        return "community_discussion"
    if any(h in full for h in BENCHMARK_HINTS):
        return "benchmark_or_spec"
    if any(h in full for h in OFFICIAL_DOC_HINTS):
        return "official_documentation"
    return "technical_article"
