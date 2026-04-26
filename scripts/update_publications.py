from pathlib import Path
from datetime import datetime, timezone
from scholarly import scholarly
import yaml
import html

SCHOLAR_ID = "xqccd64AAAAJ"

OUT = Path("_pages/publication.md")
NOTES_FILE = Path("_data/publication_notes.yml")


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
        return yaml.safe_load(f) or {}


def get_year(pub):
    year = pub.get("year", "")
    return int(year) if str(year).isdigit() else 0


def link_button(label, url):
    if not url:
        return ""
    return f'<a class="pub-btn" href="{safe_html(url)}" target="_blank">{label}</a>'


def fetch_scholar_data():
    print("Fetching Google Scholar profile...")
    author = scholarly.search_author_id(SCHOLAR_ID)

    print("Fetching citation metrics and publication list...")
    author = scholarly.fill(
        author,
        sections=["basics", "indices", "publications"],
        publication_limit=150,
    )

    publications = []

    for pub in author.get("publications", []):
        bib = pub.get("bib", {})

        title = clean_text(bib.get("title"))
        if not title:
            continue

        publications.append({
            "title": title,
            "authors": clean_text(bib.get("author")),
            "venue": clean_text(
                bib.get("journal")
                or bib.get("conference")
                or bib.get("venue")
                or bib.get("publisher")
                or bib.get("citation")
            ),
            "year": clean_text(bib.get("pub_year")),
            "citations": clean_text(pub.get("num_citations")),
            "scholar_url": clean_text(pub.get("author_pub_id")),
        })

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
  line-height: 1.2;
}
.pub-metric-label {
  font-size: 0.8rem;
  color: #64748b;
  margin-top: 0.25rem;
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
        "<!-- This page is automatically generated. -->",
        "<!-- Add optional manual details in _data/publication_notes.yml. -->",
        "",
    ]

    for pub in publications:
        title = pub["title"]
        extra = notes.get(title, {}) or {}

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

        lines.append('<div class="pub-card">')
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

    return "\n".join(lines)


def main():
    notes = load_notes()

    try:
        data = fetch_scholar_data()
    except Exception as e:
        print("Could not fetch from Google Scholar.")
        print(e)
        print("Existing publication page will stay unchanged.")
        return

    page = build_page(data, notes)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")

    print(f"Updated {OUT}")
    print(f"Number of publications: {len(data.get('publications', []))}")
    print(f"Citations: {data.get('citedby', '')}")
    print(f"h-index: {data.get('hindex', '')}")
    print(f"i10-index: {data.get('i10index', '')}")


if __name__ == "__main__":
    main()
