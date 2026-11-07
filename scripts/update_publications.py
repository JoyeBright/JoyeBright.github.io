
from pathlib import Path
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import quote
import html
import json
import re
import time
import random
import requests
import yaml

from scholarly import scholarly


# ============================================================
# CONFIGURATION
# ============================================================

SCHOLAR_ID = "xqccd64AAAAJ"

OUT = Path("_pages/publication.md")
NOTES_FILE = Path("_data/publication_notes.yml")
REPORT_FILE = Path("_data/publication_extraction_report.json")

MAX_PUBLICATIONS = 150
REQUEST_TIMEOUT = 20
MAX_RETRIES = 3

# Optional public metadata fallbacks.
USE_CROSSREF = True
USE_OPENALEX = True

# Adjust to a contact address you control if desired.
CONTACT_EMAIL = ""

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "AcademicPublicationUpdater/1.0 "
        f"(mailto:{CONTACT_EMAIL})"
        if CONTACT_EMAIL else
        "AcademicPublicationUpdater/1.0"
    ),
    "Accept": "application/json",
})


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)

    return re.sub(r"\s+", " ", str(value)).strip()


def safe_html(value):
    return html.escape(str(value), quote=True)


def to_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def normalize_title(title):
    title = clean_text(title).lower()
    return re.sub(r"[^a-z0-9]+", "", title)


def title_similarity(a, b):
    a = normalize_title(a)
    b = normalize_title(b)

    if not a or not b:
        return 0.0

    return SequenceMatcher(None, a, b).ratio()


def load_notes():
    if not NOTES_FILE.exists():
        return {}

    with NOTES_FILE.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError("Publication notes must be a YAML mapping.")

    return data


def get_year(pub):
    return to_int(pub.get("year"))


def get_citations(pub):
    return to_int(pub.get("citations"))


def retry_call(func, label, attempts=MAX_RETRIES):
    for attempt in range(1, attempts + 1):
        try:
            return func()

        except Exception as exc:
            print(
                f"[WARNING] {label}: "
                f"attempt {attempt}/{attempts}: {exc}"
            )

            if attempt == attempts:
                raise

            delay = min(30, 3 * (2 ** (attempt - 1)))
            time.sleep(delay + random.uniform(0, 1))


def get_json(url, params=None):
    response = SESSION.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()
    return response.json()


# ============================================================
# METADATA CLEANING
# ============================================================

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

    if venue and authors.lower() == venue.lower():
        return ""

    if any(p.lower() in authors.lower() for p in bad_patterns):
        return ""

    if year and year in authors and "," in authors:
        return ""

    return authors


def extract_venue(bib):
    for field in (
        "journal",
        "conference",
        "booktitle",
        "venue",
        "publisher",
    ):
        value = clean_text(bib.get(field))

        if value:
            return value

    return ""


def extract_year(bib):
    for field in ("pub_year", "year"):
        value = clean_text(bib.get(field))

        match = re.search(r"\b(?:19|20)\d{2}\b", value)

        if match:
            return match.group(0)

    return ""


def merge_missing(base, new, source):
    changed = []

    for field in (
        "authors",
        "venue",
        "year",
        "doi",
        "paper",
        "pdf",
    ):
        if not base.get(field) and new.get(field):
            base[field] = clean_text(new[field])
            changed.append(field)

    if changed:
        base.setdefault("sources", []).append({
            "source": source,
            "fields": changed,
        })

    return base


# ============================================================
# CROSSREF FALLBACK
# ============================================================

def fetch_crossref(title):
    if not USE_CROSSREF:
        return {}

    data = retry_call(
        lambda: get_json(
            "https://api.crossref.org/works",
            params={
                "query.title": title,
                "rows": 3,
                "select": (
                    "title,author,container-title,"
                    "published,DOI,URL"
                ),
            },
        ),
        f"Crossref lookup: {title}",
    )

    items = data.get("message", {}).get("items", [])

    for item in items:
        candidate_title = clean_text(item.get("title"))

        if title_similarity(title, candidate_title) < 0.92:
            continue

        authors = []

        for author in item.get("author", []):
            name = clean_text(
                " ".join([
                    author.get("given", ""),
                    author.get("family", ""),
                ])
            )

            if name:
                authors.append(name)

        year = ""

        date_parts = (
            item.get("published", {})
            .get("date-parts", [])
        )

        if date_parts and date_parts[0]:
            year = str(date_parts[0][0])

        doi = clean_text(item.get("DOI"))

        return {
            "authors": ", ".join(authors),
            "venue": clean_text(
                item.get("container-title")
            ),
            "year": year,
            "doi": (
                f"https://doi.org/{doi}"
                if doi else ""
            ),
            "paper": clean_text(item.get("URL")),
        }

    return {}


# ============================================================
# OPENALEX FALLBACK
# ============================================================

def fetch_openalex(title):
    if not USE_OPENALEX:
        return {}

    params = {
        "search": title,
        "per-page": 5,
    }

    if CONTACT_EMAIL:
        params["mailto"] = CONTACT_EMAIL

    data = retry_call(
        lambda: get_json(
            "https://api.openalex.org/works",
            params=params,
        ),
        f"OpenAlex lookup: {title}",
    )

    for item in data.get("results", []):
        candidate_title = clean_text(
            item.get("display_name")
        )

        if title_similarity(title, candidate_title) < 0.92:
            continue

        authors = []

        for entry in item.get("authorships", []):
            author = entry.get("author", {})
            name = clean_text(author.get("display_name"))

            if name:
                authors.append(name)

        primary_location = (
            item.get("primary_location") or {}
        )

        source = primary_location.get("source") or {}

        doi = clean_text(item.get("doi"))

        return {
            "authors": ", ".join(authors),
            "venue": clean_text(
                source.get("display_name")
            ),
            "year": clean_text(
                item.get("publication_year")
            ),
            "doi": doi,
            "paper": clean_text(
                primary_location.get("landing_page_url")
            ),
            "pdf": clean_text(
                primary_location.get("pdf_url")
            ),
        }

    return {}


# ============================================================
# GOOGLE SCHOLAR EXTRACTION
# ============================================================

def parse_scholar_publication(pub):
    bib = pub.get("bib", {}) or {}

    return {
        "title": clean_text(bib.get("title")),
        "authors": clean_author_field(
            bib.get("author"),
            venue=extract_venue(bib),
            year=extract_year(bib),
        ),
        "venue": extract_venue(bib),
        "year": extract_year(bib),
        "citations": clean_text(
            pub.get("num_citations", 0)
        ),
        "paper": clean_text(
            pub.get("pub_url")
        ),
        "pdf": clean_text(
            pub.get("eprint_url")
        ),
        "doi": "",
        "sources": [],
    }


def incomplete_fields(pub):
    required = ["title", "authors", "venue", "year"]

    return [
        field
        for field in required
        if not clean_text(pub.get(field))
    ]


def enrich_publication(pub):
    title = pub["title"]

    # Google Scholar detailed metadata
    try:
        filled = retry_call(
            lambda: scholarly.fill(pub["_scholar_raw"]),
            f"Scholar details: {title}",
            attempts=2,
        )

        detailed = parse_scholar_publication(filled)

        merge_missing(pub, detailed, "Google Scholar details")

    except Exception as exc:
        print(f"[WARNING] Scholar details unavailable: {exc}")

    # Crossref fallback
    if incomplete_fields(pub):
        try:
            crossref = fetch_crossref(title)
            merge_missing(pub, crossref, "Crossref")

        except Exception as exc:
            print(f"[WARNING] Crossref unavailable: {exc}")

    # OpenAlex fallback
    if incomplete_fields(pub):
        try:
            openalex = fetch_openalex(title)
            merge_missing(pub, openalex, "OpenAlex")

        except Exception as exc:
            print(f"[WARNING] OpenAlex unavailable: {exc}")

    return pub


def fetch_scholar_data():
    print("Fetching Google Scholar profile...")

    author = retry_call(
        lambda: scholarly.search_author_id(SCHOLAR_ID),
        "Scholar author lookup",
    )

    author = retry_call(
        lambda: scholarly.fill(
            author,
            sections=[
                "basics",
                "indices",
                "publications",
            ],
            publication_limit=MAX_PUBLICATIONS,
        ),
        "Scholar profile extraction",
    )

    raw_publications = author.get("publications", [])

    if not raw_publications:
        raise RuntimeError(
            "Google Scholar returned no publications. "
            "The existing page will not be overwritten."
        )

    publications = []

    for index, raw in enumerate(raw_publications, 1):
        pub = parse_scholar_publication(raw)

        if not pub["title"]:
            print(f"[WARNING] Skipping untitled record {index}")
            continue

        pub["_scholar_raw"] = raw

        print(
            f"[{index}/{len(raw_publications)}] "
            f"{pub['title']}"
        )

        # Fetch details for every publication, not only
        # those initially missing authors.
        pub = enrich_publication(pub)

        pub.pop("_scholar_raw", None)

        publications.append(pub)

        # Small delay to avoid excessive rapid requests.
        time.sleep(random.uniform(1.0, 2.0))

    publications.sort(
        key=get_year,
        reverse=True,
    )

    return {
        "citedby": author.get("citedby", ""),
        "hindex": author.get("hindex", ""),
        "i10index": author.get("i10index", ""),
        "publications": publications,
    }


# ============================================================
# YAML OVERRIDES
# ============================================================

def apply_notes(pub, notes):
    extra = notes.get(pub["title"], {}) or {}

    result = dict(pub)

    for field in (
        "authors",
        "venue",
        "year",
        "citations",
        "paper",
        "pdf",
        "doi",
        "preprint",
        "code",
        "slides",
        "video",
        "arxiv",
        "date",
        "status",
        "proceedings",
        "series",
        "pages",
        "note",
    ):
        if field in extra and extra[field] is not None:
            result[field] = clean_text(extra[field])

    return result


# ============================================================
# HTML PAGE
# ============================================================

CSS = """
<style>
.pub-metrics {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  margin: 1.2rem 0 2rem;
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
  background: white;
  box-shadow: 0 2px 8px rgba(15,23,42,0.04);
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

JS = """
<script>
document.addEventListener("DOMContentLoaded", function () {
  const select = document.getElementById("pub-sort");
  const list = document.getElementById("pub-list");

  if (!select || !list) return;

  select.addEventListener("change", function () {
    const cards = Array.from(
      list.querySelectorAll(".pub-card")
    );

    const mode = select.value;

    cards.sort(function (a, b) {
      if (mode === "year-desc") {
        return Number(b.dataset.year || 0)
             - Number(a.dataset.year || 0);
      }

      if (mode === "year-asc") {
        return Number(a.dataset.year || 0)
             - Number(b.dataset.year || 0);
      }

      if (mode === "citations-desc") {
        return Number(b.dataset.citations || 0)
             - Number(a.dataset.citations || 0);
      }

      return 0;
    });

    cards.forEach(card => list.appendChild(card));
  });
});
</script>
"""


def link_button(label, url):
    if not url:
        return ""

    return (
        f'<a class="pub-btn" '
        f'href="{safe_html(url)}" '
        f'target="_blank" '
        f'rel="noopener noreferrer">'
        f'{safe_html(label)}</a>'
    )


def build_page(data, publications):
    updated = datetime.now(
        timezone.utc
    ).strftime("%B %d, %Y, %H:%M UTC")

    metrics = [
        ("Citations", data.get("citedby", "")),
        ("h-index", data.get("hindex", "")),
        ("i10-index", data.get("i10index", "")),
        ("Publications", len(publications)),
    ]

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
        CSS,
        "",
        "I have published under the name **Javad Pourmostafa Roshan Sharami**, where *Roshan Sharami* is a suffix added to my last name.",
        "",
        f'<p class="pub-updated">Last updated: {updated}</p>',
        "",
        '<div class="pub-metrics">',
    ]

    for label, value in metrics:
        display = safe_html(
            value if value != "" else "—"
        )

        lines.append(
            '<div class="pub-metric-card">'
            f'<div class="pub-metric-number">{display}</div>'
            f'<div class="pub-metric-label">{label}</div>'
            '</div>'
        )

    lines.extend([
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
    ])

    for pub in publications:
        lines.append(
            '<div class="pub-card" '
            f'data-year="{get_year(pub)}" '
            f'data-citations="{get_citations(pub)}">'
        )

        lines.append(
            f'<div class="pub-title">'
            f'{safe_html(pub["title"])}'
            '</div>'
        )

        if pub.get("authors"):
            lines.append(
                f'<div class="pub-authors">'
                f'{safe_html(pub["authors"])}'
                '</div>'
            )

        meta = []

        for field in ("venue", "year"):
            if pub.get(field):
                meta.append(safe_html(pub[field]))

        if pub.get("citations") != "":
            meta.append(
                f'{safe_html(pub["citations"])} citations'
            )

        if meta:
            lines.append(
                f'<div class="pub-meta">'
                f'{" · ".join(meta)}'
                '</div>'
            )

        for field in (
            "date",
            "status",
            "proceedings",
            "series",
            "pages",
        ):
            if pub.get(field):
                lines.append(
                    '<div class="pub-meta">'
                    f'<strong>{field.capitalize()}:</strong> '
                    f'{safe_html(pub[field])}'
                    '</div>'
                )

        if pub.get("note"):
            lines.append(
                f'<div class="pub-note">'
                f'{safe_html(pub["note"])}'
                '</div>'
            )

        buttons = []

        for field, label in (
            ("paper", "Paper"),
            ("pdf", "PDF"),
            ("preprint", "Preprint"),
            ("code", "Code"),
            ("slides", "Slides"),
            ("video", "Video"),
            ("doi", "DOI"),
            ("arxiv", "arXiv"),
        ):
            button = link_button(label, pub.get(field))

            if button:
                buttons.append(button)

        if buttons:
            lines.append(
                '<div class="pub-links">'
                + " ".join(buttons)
                + "</div>"
            )

        lines.append("</div>")
        lines.append("")

    lines.extend([
        "</div>",
        JS,
    ])

    return "\n".join(lines)


# ============================================================
# EXTRACTION REPORT
# ============================================================

def build_report(publications):
    incomplete = []

    for pub in publications:
        missing = incomplete_fields(pub)

        if missing:
            incomplete.append({
                "title": pub["title"],
                "missing": missing,
                "sources": pub.get("sources", []),
            })

    return {
        "updated": datetime.now(
            timezone.utc
        ).isoformat(),
        "total_publications": len(publications),
        "complete_publications": (
            len(publications) - len(incomplete)
        ),
        "incomplete_publications": incomplete,
    }


# ============================================================
# MAIN
# ============================================================

def main():
    notes = load_notes()

    try:
        data = fetch_scholar_data()

    except Exception as exc:
        print("\n[ERROR] Google Scholar extraction failed.")
        print(exc)
        print("Existing publication page remains unchanged.")
        raise SystemExit(1)

    publications = [
        apply_notes(pub, notes)
        for pub in data["publications"]
    ]

    publications.sort(
        key=get_year,
        reverse=True,
    )

    report = build_report(publications)

    page = build_page(data, publications)

    OUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Write report first, then publication page.
    REPORT_FILE.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    OUT.write_text(
        page,
        encoding="utf-8",
    )

    print("\n" + "=" * 55)
    print("PUBLICATION EXTRACTION SUMMARY")
    print("=" * 55)

    print(
        f"Total publications: "
        f"{report['total_publications']}"
    )

    print(
        f"Complete metadata: "
        f"{report['complete_publications']}"
    )

    print(
        f"Incomplete metadata: "
        f"{len(report['incomplete_publications'])}"
    )

    print(f"Citations: {data.get('citedby', '')}")
    print(f"h-index: {data.get('hindex', '')}")
    print(f"i10-index: {data.get('i10index', '')}")

    for item in report["incomplete_publications"]:
        print(
            f"\n[INCOMPLETE] {item['title']}\n"
            f"Missing: {', '.join(item['missing'])}"
        )

    print(f"\nPublication page: {OUT}")
    print(f"Extraction report: {REPORT_FILE}")

    if report["incomplete_publications"]:
        print(
            "\n[WARNING] Page generated, but some "
            "publication metadata is incomplete."
        )
    else:
        print("\n[SUCCESS] All required metadata present.")


if __name__ == "__main__":
    main()
