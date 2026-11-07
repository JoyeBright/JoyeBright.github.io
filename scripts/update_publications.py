
from pathlib import Path
from datetime import datetime, timezone
from scholarly import scholarly
import yaml
import html
import json
import os
import re
import sys
import time
import tempfile
import subprocess
import traceback
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

MAX_SECONDS = 300
API_TIMEOUT = 9
MAX_RESULTS = 6

SCHOLAR_ID = "xqccd64AAAAJ"

OUT = Path("_pages/publication.md")
NOTES_FILE = Path("_data/publication_notes.yml")


def clean_text(value):
    if not value:
        return ""
    return str(value).replace("\n", " ").strip()


def safe_html(value):
    return html.escape(str(value), quote=True)


def load_notes():
    if not NOTES_FILE.exists():
        return {}
    with NOTES_FILE.open("r", encoding="utf-8") as f:
        return as_dict(yaml.safe_load(f))


def get_year(pub):
    year = pub.get("year", "")
    return int(year) if str(year).isdigit() else 0


def get_citations(pub):
    citations = pub.get("citations", "")
    return int(citations) if str(citations).isdigit() else 0


def link_button(label, url):
    url = safe_url(url)
    if not url:
        return ""
    return f'<a class="pub-btn" href="{safe_html(url)}" target="_blank" rel="noopener noreferrer">{label}</a>'


def safe_url(value):
    url = clean_text(value)
    parsed = urlsplit(url)
    return url if parsed.scheme in ("https", "http") and parsed.netloc else ""


def display_authors(authors, limit=6):
    """Preserve the original author order; truncate only the displayed list."""
    raw = clean_text(authors)
    if not raw:
        return ""
    names = [name.strip() for name in re.split(r"\s+and\s+|\s*;\s*|\s*,\s*", raw, flags=re.I) if name.strip()]
    return ", ".join(names[:limit]) + (", …" if len(names) > limit else "")


def clean_author_field(authors, venue="", year=""):
    authors = clean_text(authors)

    if not authors:
        return ""

    bad_patterns = [
        "Proceedings of",
        "International Conference",
        "Conference on",
        "Journal of",
        "arXiv",
        "Springer",
        "Lecture Notes",
        "Transactions on",
        "Association for",
    ]

    if venue and authors == venue:
        return ""

    if any(pattern.lower() in authors.lower() for pattern in bad_patterns):
        return ""

    if year and str(year) in authors and "," in authors:
        return ""

    return authors


def as_dict(value):
    return value if isinstance(value, dict) else {}


def normalized_title(value):
    value = unicodedata.normalize("NFKD", clean_text(value)).casefold()
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def match_score(requested, candidate, expected_year="", candidate_year=""):
    a, b = normalized_title(requested), normalized_title(candidate)
    if not a or not b:
        return 0.0
    if expected_year and candidate_year:
        try:
            if abs(int(expected_year) - int(candidate_year)) > 1:
                return 0.0
        except (TypeError, ValueError):
            pass
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def request_json(url, params):
    full_url = url + "?" + urlencode(params)
    request = Request(full_url, headers={"User-Agent": "AcademicPublicationsUpdater/1.0 (metadata lookup)", "Accept": "application/json"})
    with urlopen(request, timeout=API_TIMEOUT) as response:
        return json.load(response)


def crossref_candidates(title):
    result = request_json("https://api.crossref.org/works", {"query.bibliographic": title, "rows": MAX_RESULTS})
    for item in as_dict(as_dict(result).get("message")).get("items") or []:
        item = as_dict(item)
        titles = item.get("title") or []
        title_value = titles[0] if isinstance(titles, list) and titles else ""
        dates = as_dict(item.get("published") or item.get("issued") or item.get("created")).get("date-parts") or []
        year = str(dates[0][0]) if dates and dates[0] else ""
        authors = []
        for author in item.get("author") or []:
            author = as_dict(author)
            name = clean_text(" ".join(filter(None, (author.get("given"), author.get("family")))))
            if name:
                authors.append(name)
        venues = item.get("container-title") or []
        venue = venues[0] if isinstance(venues, list) and venues else ""
        yield {"title": title_value, "authors": ", ".join(authors), "venue": clean_text(venue), "year": year, "source": "Crossref", "url": safe_url(item.get("URL") or ("https://doi.org/" + item["DOI"] if item.get("DOI") else ""))}


def openalex_candidates(title):
    result = request_json("https://api.openalex.org/works", {"search.title": title, "per_page": MAX_RESULTS})
    for item in as_dict(result).get("results") or []:
        item = as_dict(item)
        names = []
        for authorship in item.get("authorships") or []:
            authorship = as_dict(authorship)
            name = clean_text(as_dict(authorship.get("author")).get("display_name") or authorship.get("raw_author_name"))
            if name:
                names.append(name)
        location = as_dict(item.get("primary_location"))
        source = as_dict(location.get("source"))
        yield {"title": item.get("display_name") or item.get("title") or "", "authors": ", ".join(names), "venue": clean_text(source.get("display_name")), "year": str(item.get("publication_year") or ""), "source": "OpenAlex", "url": safe_url(location.get("landing_page_url") or item.get("doi"))}


def recover_metadata(title, year, authors, venue):
    missing = {"authors": not bool(authors), "venue": not bool(venue), "year": not bool(year)}
    recovered = {"authors": "", "venue": "", "year": "", "url": ""}
    for source, lookup in (("Crossref", crossref_candidates), ("OpenAlex", openalex_candidates)):
        if not any(missing[field] and not recovered[field] for field in missing):
            break
        try:
            candidates = list(lookup(title))
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError, OSError) as exc:
            print(f"[WARNING] {source} lookup failed for {title}: {exc}", flush=True)
            continue
        ranked = sorted(((match_score(title, item.get("title"), year, item.get("year")), item) for item in candidates), key=lambda pair: pair[0], reverse=True)
        if not ranked or ranked[0][0] < 0.94:
            continue
        score, best = ranked[0]
        if len(ranked) > 1 and ranked[1][0] >= 0.94 and score - ranked[1][0] < 0.025 and ranked[1][1].get("authors") != best.get("authors"):
            print(f"[WARNING] Ambiguous {source} match for {title}; not importing metadata", flush=True)
            continue
        if not recovered["url"] and best.get("url"):
            recovered["url"] = best["url"]
        for field in missing:
            if missing[field] and not recovered[field] and best.get(field):
                recovered[field] = clean_text(best[field])
                print(f"[FALLBACK] {source} supplied {field}: {title}", flush=True)
    return recovered


def fetch_scholar_data():
    print("Fetching Google Scholar profile...", flush=True)
    author = as_dict(scholarly.search_author_id(SCHOLAR_ID))
    if not author:
        raise RuntimeError("Google Scholar returned no valid author profile")
    print("Fetching citation metrics and publication list...", flush=True)
    author = as_dict(scholarly.fill(author, sections=["basics", "indices", "publications"], publication_limit=150))
    if not author:
        raise RuntimeError("Google Scholar returned no publication profile")
    raw_pubs = author.get("publications") or []
    if not isinstance(raw_pubs, list) or not raw_pubs:
        raise RuntimeError("Google Scholar returned no publications; preserving existing page")
    publications = []
    detail_broken = False
    for raw in raw_pubs:
        pub = as_dict(raw)
        bib = as_dict(pub.get("bib"))
        title = clean_text(bib.get("title"))
        if not title:
            continue
        year = clean_text(bib.get("pub_year") or bib.get("year"))
        venue = clean_text(bib.get("journal") or bib.get("conference") or bib.get("venue") or bib.get("publisher"))
        # A formatted citation is not necessarily a journal/conference name.
        authors = clean_author_field(bib.get("author"), venue=venue, year=year)
        if not authors and not detail_broken:
            try:
                print(f"Trying Google Scholar details: {title}", flush=True)
                detailed = as_dict(scholarly.fill(pub))
                detailed_bib = as_dict(detailed.get("bib"))
                detail_venue = clean_text(detailed_bib.get("journal") or detailed_bib.get("conference") or detailed_bib.get("venue") or detailed_bib.get("publisher"))
                authors = clean_author_field(detailed_bib.get("author"), venue=detail_venue or venue, year=year)
                venue = venue or detail_venue
                year = year or clean_text(detailed_bib.get("pub_year") or detailed_bib.get("year"))
            except Exception as exc:
                print(f"[WARNING] Scholar details unavailable for {title}: {exc}", flush=True)
                if isinstance(exc, AttributeError) and "NoneType" in str(exc):
                    detail_broken = True
                    print("[WARNING] Scholar detail parser failed; skipping further detail requests", flush=True)
        paper_url = safe_url(pub.get("pub_url") or bib.get("url"))
        if not authors or not venue or not year or not paper_url:
            recovered = recover_metadata(title, year, authors, venue)
            authors = authors or clean_author_field(recovered["authors"], venue=venue or recovered["venue"], year=year)
            venue = venue or recovered["venue"]
            year = year or recovered["year"]
            paper_url = paper_url or recovered["url"]
        publications.append({"title": title, "authors": authors, "venue": venue, "year": year, "citations": clean_text(pub.get("num_citations")), "url": paper_url})
    if not publications:
        raise RuntimeError("No valid publication titles found; preserving existing page")
    publications.sort(key=get_year, reverse=True)
    return {"citedby": author.get("citedby", ""), "hindex": author.get("hindex", ""), "i10index": author.get("i10index", ""), "publications": publications}


def build_page(data, notes):
    last_updated = datetime.now(timezone.utc).strftime("%B %d, %Y, %H:%M UTC")

    citedby = data.get("citedby", "")
    hindex = data.get("hindex", "")
    i10index = data.get("i10index", "")
    publications = data.get("publications", [])

    css = """
<style>
.pub-metrics {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  margin: 1.2rem 0 2rem 0;
}
.pub-metric-card {
  flex: 1;
  min-width: 140px;
  padding: 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #f8fafc;
  text-align: center;
}
.pub-metric-number {
  font-size: 1.45rem;
  font-weight: 700;
}
.pub-metric-label {
  font-size: 0.8rem;
  color: #64748b;
}
.pub-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin: 1.5rem 0;
  padding: 0.8rem 1rem;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #f8fafc;
}
.pub-toolbar label {
  font-size: 0.9rem;
  font-weight: 600;
}
.pub-toolbar select {
  padding: 0.4rem 0.65rem;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  background: white;
}
.pub-card {
  padding: 1.15rem 1.25rem;
  margin: 1.15rem 0;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.pub-title {
  font-size: 1.12rem;
  font-weight: 700;
  margin-bottom: 0.45rem;
}
.pub-title-link { color: inherit; text-decoration: none; }
.pub-title-link:hover { color: #2563eb; text-decoration: underline; }
.pub-card:hover { border-color: #bfdbfe; box-shadow: 0 6px 20px rgba(15, 23, 42, 0.08); }
.pub-authors {
  font-size: 0.92rem;
  color: #334155;
  margin-bottom: 0.35rem;
}
.pub-meta {
  font-size: 0.88rem;
  color: #475569;
  margin-bottom: 0.65rem;
}
.pub-note {
  font-size: 0.88rem;
  color: #334155;
  background: #f8fafc;
  border-left: 3px solid #cbd5e1;
  padding: 0.55rem 0.75rem;
  margin: 0.7rem 0;
}
.pub-links {
  margin-top: 0.7rem;
}
.pub-btn {
  display: inline-block;
  padding: 0.28rem 0.62rem;
  margin: 0.15rem 0.25rem 0.15rem 0;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  font-size: 0.78rem;
  text-decoration: none;
}
.pub-btn:hover {
  background: #f1f5f9;
}
.pub-updated {
  font-size: 0.8rem;
  color: #64748b;
}
</style>
"""

    js = """
<script>
document.addEventListener("DOMContentLoaded", function () {
  const select = document.getElementById("pub-sort");
  const list = document.getElementById("pub-list");

  if (!select || !list) return;

  function sortPublications() {
    const cards = Array.from(list.querySelectorAll(".pub-card"));
    const mode = select.value;

    cards.sort(function (a, b) {
      if (mode === "year-desc") {
        return Number(b.dataset.year || 0) - Number(a.dataset.year || 0);
      }
      if (mode === "year-asc") {
        return Number(a.dataset.year || 0) - Number(b.dataset.year || 0);
      }
      if (mode === "citations-desc") {
        return Number(b.dataset.citations || 0) - Number(a.dataset.citations || 0);
      }
      return 0;
    });

    cards.forEach(card => list.appendChild(card));
  }

  select.addEventListener("change", sortPublications);
});
</script>
"""

    lines = [
        "---",
        "title: Publications",
        "layout: archive",
        "classes: wide",
        "permalink: /publication/",
        "author_profile: true",
        "excerpt: This page shows a list of Javad Pourmostafa's papers and talks.",
        "---",
        "",
        css,
        "",
        "I have published under the name **Javad Pourmostafa Roshan Sharami**, where *Roshan Sharami* is a suffix added to my last name.",
        "",
        f"<p class='pub-updated'><em>Last updated: {last_updated}</em></p>",
        "",
        '<div class="pub-metrics">',
        f'<div class="pub-metric-card"><div class="pub-metric-number">{safe_html(citedby or "—")}</div><div class="pub-metric-label">Citations</div></div>',
        f'<div class="pub-metric-card"><div class="pub-metric-number">{safe_html(hindex or "—")}</div><div class="pub-metric-label">h-index</div></div>',
        f'<div class="pub-metric-card"><div class="pub-metric-number">{safe_html(i10index or "—")}</div><div class="pub-metric-label">i10-index</div></div>',
        f'<div class="pub-metric-card"><div class="pub-metric-number">{len(publications)}</div><div class="pub-metric-label">Publications</div></div>',
        "</div>",
        "",
        '<div class="pub-toolbar">',
        '<label for="pub-sort">Sort publications</label>',
        '<select id="pub-sort">',
        '<option value="year-desc">Newest first</option>',
        '<option value="year-asc">Oldest first</option>',
        '<option value="citations-desc">Most cited first</option>',
        "</select>",
        "</div>",
        "",
        '<div id="pub-list">',
    ]

    for pub in publications:
        title = pub["title"]
        extra = as_dict(notes.get(title, {}))

        authors = extra.get("authors") or pub.get("authors", "")
        venue = extra.get("venue") or pub.get("venue", "")
        year = extra.get("year") or pub.get("year", "")
        citations = extra.get("citations") if extra.get("citations") is not None else pub.get("citations", "")
        paper_url = safe_url(extra.get("paper") or extra.get("doi") or pub.get("url"))

        links = [
            link_button("Paper", paper_url),
            link_button("PDF", extra.get("pdf")),
            link_button("Preprint", extra.get("preprint")),
            link_button("Code", extra.get("code")),
            link_button("Slides", extra.get("slides")),
            link_button("Video", extra.get("video")),
            link_button("DOI", extra.get("doi")),
            link_button("arXiv", extra.get("arxiv")),
        ]
        links = [x for x in links if x]

        year_num = get_year({"year": year})
        citation_num = get_citations({"citations": citations})

        lines.append(
            f'<div class="pub-card" '
            f'data-year="{year_num}" '
            f'data-citations="{citation_num}">'
        )

        if paper_url:
            lines.append(f'<div class="pub-title"><a class="pub-title-link" href="{safe_html(paper_url)}" target="_blank" rel="noopener noreferrer">{safe_html(title)}</a></div>')
        else:
            lines.append(f'<div class="pub-title">{safe_html(title)}</div>')

        if authors:
            lines.append(f'<div class="pub-authors" title="{safe_html(authors)}">{safe_html(display_authors(authors))}</div>')

        meta_parts = []
        if venue:
            meta_parts.append(safe_html(venue))
        if year:
            meta_parts.append(safe_html(year))
        if citations:
            meta_parts.append(f"{safe_html(citations)} citations")

        if meta_parts:
            lines.append(f'<div class="pub-meta">{" · ".join(meta_parts)}</div>')

        for field in ["date", "status", "proceedings", "series", "pages"]:
            if extra.get(field):
                lines.append(
                    f'<div class="pub-meta"><strong>{field.capitalize()}:</strong> {safe_html(extra[field])}</div>'
                )

        if extra.get("note"):
            lines.append(f'<div class="pub-note">{safe_html(extra["note"])}</div>')

        if links:
            lines.append('<div class="pub-links">' + " ".join(links) + "</div>")

        lines.append("</div>")
        lines.append("")

    lines.append("</div>")
    lines.append(js)

    return "\n".join(lines)


def worker(output_path):
    try:
        data = fetch_scholar_data()
        Path(output_path).write_text(json.dumps({"ok": True, "data": data}), encoding="utf-8")
    except Exception:
        Path(output_path).write_text(json.dumps({"ok": False, "error": traceback.format_exc()}), encoding="utf-8")
        raise


def main():
    # A subprocess gives a true deadline even when scholarly hangs inside a request.
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        worker(sys.argv[2])
        return 0
    notes = load_notes()
    fd, temp_path = tempfile.mkstemp(prefix="scholar_publications_", suffix=".json")
    os.close(fd)
    try:
        print(f"Starting extraction (hard timeout: {MAX_SECONDS} seconds)...", flush=True)
        try:
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", temp_path], timeout=MAX_SECONDS, check=False)
        except subprocess.TimeoutExpired:
            print("[TIMEOUT] Google Scholar extraction exceeded 300 seconds; existing page preserved", flush=True)
            return 124
        try:
            result = json.loads(Path(temp_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print("[ERROR] Extraction produced no usable result; existing page preserved", flush=True)
            return 1
        if not result.get("ok"):
            print("[ERROR] Extraction failed; existing page preserved", flush=True)
            print(result.get("error", "Unknown error"), flush=True)
            return 1
        data = result["data"]
        page = build_page(data, notes)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: never leave a partially generated page.
        fd, page_tmp = tempfile.mkstemp(prefix=".publication_", suffix=".md", dir=str(OUT.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(page)
            os.replace(page_tmp, OUT)
        finally:
            if os.path.exists(page_tmp):
                os.unlink(page_tmp)
        missing = []
        for pub in data["publications"]:
            override = as_dict(notes.get(pub["title"]))
            fields = [field for field in ("authors", "venue", "year") if not (override.get(field) or pub.get(field))]
            if fields:
                missing.append((pub["title"], fields))
        print(f"Updated {OUT}")
        print(f"Number of publications: {len(data['publications'])}")
        print(f"Citations: {data.get('citedby', '')}")
        print(f"h-index: {data.get('hindex', '')}")
        print(f"i10-index: {data.get('i10index', '')}")
        if missing:
            print(f"[INCOMPLETE] {len(missing)} publication(s) still missing metadata:")
            for title, fields in missing:
                print(f"  - {title}: {', '.join(fields)}")
            return 0  # Publish the usable page; log accurately that metadata is incomplete.
        print("[SUCCESS] All publication author, venue and year fields are present")
        return 0
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


if __name__ == "__main__":
    sys.exit(main())
