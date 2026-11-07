
from pathlib import Path
from datetime import datetime, timezone
from scholarly import scholarly
import yaml
import html
import signal
import sys
import json
import re
from difflib import SequenceMatcher
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SCHOLAR_ID = "xqccd64AAAAJ"

OUT = Path("_pages/publication.md")
NOTES_FILE = Path("_data/publication_notes.yml")
MAX_SECONDS = 300


def clean_text(value):
    if not value:
        return ""
    return str(value).replace("\n", " ").strip()


def safe_html(value):
    return html.escape(str(value), quote=False)


def load_notes():
    if not NOTES_FILE.exists():
        return {}
    with NOTES_FILE.open("r", encoding="utf-8") as f:
        notes = yaml.safe_load(f) or {}
    if not isinstance(notes, dict):
        raise ValueError("Publication notes must be a YAML mapping keyed by title")
    return notes


def get_year(pub):
    year = pub.get("year", "")
    return int(year) if str(year).isdigit() else 0


def get_citations(pub):
    citations = pub.get("citations", "")
    return int(citations) if str(citations).isdigit() else 0


def link_button(label, url):
    if not url:
        return ""
    return f'<a class="pub-btn" href="{safe_html(url)}" target="_blank">{label}</a>'


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

    if year and year in authors and "," in authors:
        return ""

    return authors


def normalize_title(value):
    return " ".join(re.findall(r"[a-z0-9]+", clean_text(value).casefold()))


def fetch_json(url):
    request = Request(url, headers={"User-Agent": "AcademicPublicationUpdater/1.0 (metadata lookup)"})
    with urlopen(request, timeout=8) as response:
        return json.load(response)


def fallback_metadata(title, year="", need_authors=True, need_venue=True, need_year=True):
    """Crossref first, OpenAlex second; never use their citation counts."""
    result = {"authors": "", "venue": "", "year": ""}
    expected = normalize_title(title)

    def matches(candidate_title, candidate_year):
        actual = normalize_title(candidate_title)
        return (bool(actual) and
                SequenceMatcher(None, expected, actual).ratio() >= 0.94 and
                not (year and candidate_year and str(year) != str(candidate_year)))

    try:
        query = urlencode({"query.title": title, "rows": 3})
        payload = fetch_json("https://api.crossref.org/works?" + query)
        message = payload.get("message") or {} if isinstance(payload, dict) else {}
        for item in message.get("items") or []:
            if not isinstance(item, dict):
                continue
            titles = item.get("title") or []
            candidate = titles[0] if isinstance(titles, list) and titles else ""
            published = item.get("published") or item.get("issued") or {}
            dates = published.get("date-parts") or [] if isinstance(published, dict) else []
            candidate_year = str(dates[0][0]) if dates and dates[0] else ""
            if not matches(candidate, candidate_year):
                continue
            people = []
            for person in item.get("author") or []:
                if isinstance(person, dict):
                    name = clean_text(" ".join(filter(None, [person.get("given"), person.get("family")])))
                    if name:
                        people.append(name)
            venues = item.get("container-title") or []
            if need_authors:
                result["authors"] = ", ".join(people)
            if need_venue and isinstance(venues, list) and venues:
                result["venue"] = clean_text(venues[0])
            if need_year:
                result["year"] = candidate_year
            break
    except Exception as exc:
        print(f"[WARNING] Crossref lookup for {title}: {exc}", flush=True)

    if ((need_authors and not result["authors"]) or
        (need_venue and not result["venue"]) or
        (need_year and not result["year"])):
        try:
            query = urlencode({"search": title, "per-page": 3})
            payload = fetch_json("https://api.openalex.org/works?" + query)
            items = payload.get("results") or [] if isinstance(payload, dict) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                candidate_year = str(item.get("publication_year") or "")
                if not matches(item.get("display_name", ""), candidate_year):
                    continue
                if need_authors and not result["authors"]:
                    people = []
                    for authorship in item.get("authorships") or []:
                        person = authorship.get("author") or {} if isinstance(authorship, dict) else {}
                        if isinstance(person, dict) and person.get("display_name"):
                            people.append(clean_text(person["display_name"]))
                    result["authors"] = ", ".join(people)
                if need_venue and not result["venue"]:
                    location = item.get("primary_location") or {}
                    source = location.get("source") or {} if isinstance(location, dict) else {}
                    if isinstance(source, dict):
                        result["venue"] = clean_text(source.get("display_name"))
                if need_year and not result["year"]:
                    result["year"] = candidate_year
                break
        except Exception as exc:
            print(f"[WARNING] OpenAlex lookup for {title}: {exc}", flush=True)
    return result


def fetch_scholar_data():
    print("Fetching Google Scholar profile...", flush=True)
    author = scholarly.search_author_id(SCHOLAR_ID)
    if not isinstance(author, dict):
        raise RuntimeError("Google Scholar returned no valid author profile")

    print("Fetching citation metrics and publication list...", flush=True)
    author = scholarly.fill(
        author,
        sections=["basics", "indices", "publications"],
        publication_limit=150,
    )

    if not isinstance(author, dict):
        raise RuntimeError("Google Scholar returned invalid profile details")
    if not isinstance(author.get("publications"), list) or not author["publications"]:
        raise RuntimeError("Google Scholar returned no publications; refusing to overwrite the page")

    publications = []
    detail_lookup_broken = False

    for pub in author.get("publications", []):
        if not isinstance(pub, dict):
            continue
        bib = pub.get("bib") or {}
        if not isinstance(bib, dict):
            bib = {}

        title = clean_text(bib.get("title"))
        if not title:
            continue

        year = clean_text(bib.get("pub_year"))
        citation_text = clean_text(bib.get("citation"))

        venue = clean_text(
            bib.get("journal")
            or bib.get("conference")
            or bib.get("venue")
            or bib.get("publisher")
            or citation_text
        )

        authors = clean_author_field(
            bib.get("author"),
            venue=venue,
            year=year,
        )

        # Try richer publication metadata only when authors are missing.
        # This is slower, but improves author extraction.
        if not authors and not detail_lookup_broken:
            try:
                print(f"Trying to fetch authors for: {title}")
                filled_pub = scholarly.fill(pub)
                filled_bib = filled_pub.get("bib") if isinstance(filled_pub, dict) else None
                if not isinstance(filled_bib, dict):
                    filled_bib = {}

                filled_venue = clean_text(
                    filled_bib.get("journal")
                    or filled_bib.get("conference")
                    or filled_bib.get("venue")
                    or filled_bib.get("publisher")
                    or venue
                )

                filled_authors = clean_author_field(
                    filled_bib.get("author"),
                    venue=filled_venue,
                    year=year,
                )

                if filled_authors:
                    authors = filled_authors

                if filled_venue:
                    venue = filled_venue

            except Exception as e:
                print(f"Could not fetch detailed authors for {title}: {e}")
                if isinstance(e, (AttributeError, TypeError)):
                    detail_lookup_broken = True
                    print("Scholar detail parser appears broken; skipping further detail requests.")

        # Use external repositories only for fields Scholar could not provide.
        # Citation text is not a reliable venue; prefer a verified repository venue.
        has_structured_venue = bool(bib.get("journal") or bib.get("conference") or bib.get("venue") or bib.get("publisher"))
        if not authors or not year or not has_structured_venue:
            recovered = fallback_metadata(title, year, not bool(authors), not has_structured_venue, not bool(year))
            if any(recovered.values()):
                if not authors:
                    authors = clean_author_field(recovered.get("authors"), venue=recovered.get("venue", ""), year=year)
                if not has_structured_venue and recovered.get("venue"):
                    venue = recovered["venue"]
                if not year:
                    year = recovered.get("year", "")
                print(f"[FALLBACK] Recovered available metadata for: {title}", flush=True)

        publications.append({
            "title": title,
            "authors": authors,
            "venue": venue,
            "year": year,
            "citations": clean_text(pub.get("num_citations")),
        })

    if not publications:
        raise RuntimeError("No valid publication titles found; refusing to overwrite the page")

    if not publications:
        raise RuntimeError("No usable publication titles; preserving the existing page")
    publications.sort(key=get_year, reverse=True)

    return {
        "citedby": author.get("citedby", ""),
        "hindex": author.get("hindex", ""),
        "i10index": author.get("i10index", ""),
        "publications": publications,
    }


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
        extra = notes.get(title, {}) or {}
        if not isinstance(extra, dict):
            extra = {}

        authors = extra.get("authors") or pub.get("authors", "")
        venue = extra.get("venue") or pub.get("venue", "")
        year = extra.get("year") or pub.get("year", "")
        citations = extra.get("citations") or pub.get("citations", "")

        links = [
            link_button("Paper", extra.get("paper")),
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

        lines.append(f'<div class="pub-title">{safe_html(title)}</div>')

        if authors:
            lines.append(f'<div class="pub-authors">{safe_html(authors)}</div>')

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


class ExtractionTimeout(Exception):
    pass


def timeout_handler(signum, frame):
    raise ExtractionTimeout(f"Google Scholar extraction exceeded {MAX_SECONDS} seconds")


def main():
    notes = load_notes()
    previous_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(MAX_SECONDS)
    try:
        data = fetch_scholar_data()
    except ExtractionTimeout as e:
        print(f"[TIMEOUT] {e}. Existing page preserved.", flush=True)
        return 124
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}. Existing page preserved.", flush=True)
        return 1
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)

    try:
        page = build_page(data, notes)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        temporary = OUT.with_suffix(OUT.suffix + ".tmp")
        temporary.write_text(page, encoding="utf-8")
        temporary.replace(OUT)
    except Exception as exc:
        print(f"[ERROR] Could not generate publication page: {exc}", flush=True)
        return 1

    incomplete = []
    for pub in data["publications"]:
        override = notes.get(pub["title"], {}) or {}
        if not isinstance(override, dict):
            override = {}
        missing = [field for field in ("authors", "venue", "year")
                   if not (override.get(field) or pub.get(field))]
        if missing:
            incomplete.append((pub["title"], missing))
    print(f"Updated {OUT}")
    print(f"Number of publications: {len(data['publications'])}")
    print(f"Citations: {data.get('citedby', '')}")
    print(f"h-index: {data.get('hindex', '')}")
    print(f"i10-index: {data.get('i10index', '')}")
    if incomplete:
        print(f"[INCOMPLETE] {len(incomplete)} publication(s) missing authors, venue or year in Scholar data:")
        for title, missing in incomplete:
            print(f"  - {title}: {', '.join(missing)}")
        print("Add verified overrides to the optional publication_notes.yml for any remaining gaps.")
    else:
        print("[SUCCESS] All publications have authors, venue and year.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
