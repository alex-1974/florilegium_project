from __future__ import annotations

import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


PDF_HINT_PATTERN = re.compile(
    r"(\.pdf($|\?)|/download\b|/bitstream\b|viewcontent\.cgi|/document/|/file/)",
    re.IGNORECASE,
)

USER_AGENT = "BVILLAGE-Crawler/0.2"
TIMEOUT = 20


class PageFetcher:
    def __init__(self):
        self.timeout = TIMEOUT
        self.pause_seconds = 0.0

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def fetch(self, url):
        try:
            r = self.session.get(
                url,
                timeout=self.timeout,
                allow_redirects=True,
            )

            if r.status_code != 200:
                return None

            content_type = r.headers.get("content-type", "")

            return {
                "url": r.url,
                "html": r.text,
                "content_type": content_type,
            }
        except Exception:
            return None


class PageParser:
    def parse(self, url, html):
        soup = BeautifulSoup(html, "lxml")

        title = self._extract_title(soup)
        h1 = self._extract_h1(soup)
        text = self._extract_text(soup)
        links = self._extract_links(url, soup)

        return {
            "title": title,
            "h1": h1,
            "text": text,
            "links": links,
        }

    def _extract_title(self, soup):
        t = soup.find("title")
        return t.get_text(strip=True) if t else ""

    def _extract_h1(self, soup):
        out = []
        for node in soup.find_all("h1"):
            txt = node.get_text(" ", strip=True)
            if txt:
                out.append(txt)
        return out

    def _extract_text(self, soup):
        blocks = []

        for tag_name in ("p", "li"):
            for node in soup.find_all(tag_name):
                txt = node.get_text(" ", strip=True)
                if txt:
                    blocks.append(txt)

        return "\n".join(blocks)

    def _extract_links(self, base_url, soup):
        links = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            url = urljoin(base_url, href)
            anchor = a.get_text(" ", strip=True)
            is_pdf = bool(PDF_HINT_PATTERN.search(url))
            context = self._extract_link_context(a)

            links.append({
                "url": url,
                "anchor": anchor,
                "is_pdf": is_pdf,
                "context": context,
            })

        return links

    def _extract_link_context(self, a_tag):
        parent = a_tag.parent
        if parent is None:
            return a_tag.get_text(" ", strip=True)

        txt = parent.get_text(" ", strip=True)
        return txt[:400]
