#!/usr/bin/env python3
"""Validate the actual deployment output using only Python's standard library."""
import json
import struct
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "_site"
ORIGIN = "https://alexroan.co.uk"
EXPECTED = {"index.html", "404.html", "robots.txt", "sitemap.xml", "llms.txt",
            "about.md", "profile.json", "assets/style.css", "assets/theme.js", "assets/favicon.svg",
            "assets/social-card.png", "assets/portrait.jpeg"}


def require(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


class Page(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.tags, self.ids, self.text, self.structured = [], [], [], []
        self.in_schema = False
        self.in_script = False
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        self.tags.append((tag, data))
        if "id" in data:
            self.ids.append(data["id"])
        require(not any(key.startswith("on") for key in data), "inline event handler")
        require("style" not in data, "inline style violates CSP")
        require(tag not in {"iframe", "form", "object", "embed", "base"}, f"unexpected {tag}")
        if tag == "script":
            self.in_schema = data.get("type") == "application/ld+json" and "src" not in data
            self.in_script = not self.in_schema
            require(self.in_schema or (data.get("src") == "/assets/theme.js" and
                    data.get("type", "text/javascript") == "text/javascript"), "unexpected script")

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_schema = False
            self.in_script = False

    def handle_data(self, data):
        if self.in_script:
            require(not data.strip(), "inline executable script")
            return
        (self.structured if self.in_schema else self.text).append(data)


actual = {str(p.relative_to(SITE)) for p in SITE.rglob("*") if p.is_file()}
require(actual == EXPECTED, f"publication file set differs: {actual ^ EXPECTED}")
require(not any(p.is_symlink() for p in SITE.rglob("*")), "symlink in artifact")
pages = {}
for filename in ("index.html", "404.html"):
    source = (SITE / filename).read_text()
    require("{{" not in source and "{%" not in source, f"unrendered Liquid in {filename}")
    page = pages[filename] = Page(source)
    require(len(page.ids) == len(set(page.ids)), f"duplicate ID in {filename}")
    require(sum(tag == "h1" for tag, _ in page.tags) == 1, f"one H1 required in {filename}")
    require(sum(tag == "main" for tag, _ in page.tags) == 1, f"main landmark missing in {filename}")
    meta = {a.get("name", a.get("http-equiv", a.get("property"))): a.get("content")
            for tag, a in page.tags if tag == "meta"}
    require(80 <= len(meta.get("description", "")) <= 170, f"description length in {filename}")
    policy = {part.strip().split()[0]: part.strip().split()[1:]
              for part in meta.get("Content-Security-Policy", "").split(";") if part.strip()}
    require(policy.get("default-src") == ["'none'"] and policy.get("script-src") == ["'self'"] and
            policy.get("script-src-attr") == ["'none'"] and policy.get("connect-src") == ["'none'"],
            "restrictive CSP missing")
    require(sum(tag == "script" and attrs.get("src") == "/assets/theme.js"
                for tag, attrs in page.tags) == 1, "theme script missing or duplicated")
    toggle = [attrs for tag, attrs in page.tags if tag == "button" and attrs.get("id") == "theme-toggle"]
    require(len(toggle) == 1 and toggle[0].get("type") == "button" and
            toggle[0].get("aria-pressed") == "false" and "hidden" in toggle[0], "accessible theme toggle missing")
    portraits = [attrs for tag, attrs in page.tags if tag == "img" and attrs.get("class") == "portrait"]
    require(len(portraits) == 1 and portraits[0].get("src") == "/assets/portrait.jpeg" and
            portraits[0].get("alt") == "Alex Roan" and portraits[0].get("width") == "52" and
            portraits[0].get("height") == "52", "portrait markup missing")
    require(meta.get("referrer") == "no-referrer", "referrer policy missing")
    require(("noindex" in meta.get("robots", "")) == (filename == "404.html"), "indexing policy mismatch")
    links = [a for tag, a in page.tags if tag == "link" and a.get("rel") == "canonical"]
    require(len(links) == 1 and links[0]["href"] == ORIGIN + ("/" if filename == "index.html" else "/404.html"), "canonical URL mismatch")

for filename, page in pages.items():
    for tag, attrs in page.tags:
        for key in ("href", "src"):
            if key not in attrs:
                continue
            url = urlsplit(attrs[key])
            if url.scheme == "mailto":
                require(tag == "a" and key == "href" and attrs[key] == "mailto:alex@cyfrin.io",
                        "unexpected email link")
                continue
            require(url.scheme in {"", "https"}, f"unsafe URL {attrs[key]}")
            if url.netloc and url.netloc != "alexroan.co.uk":
                require(tag == "a", f"third-party resource: {attrs[key]}")
                continue
            target = (url.path.lstrip("/") or "index.html") if url.path else filename
            require(target in actual, f"broken local link: {attrs[key]}")
            if url.fragment:
                require(target in pages and unquote(url.fragment) in pages[target].ids, f"broken anchor: {attrs[key]}")

schema = json.loads((SITE / "profile.json").read_text())
inline = json.loads("".join(pages["index.html"].structured))
require(inline == schema, "inline and standalone profile differ")
require(schema["@type"] == "ProfilePage" and schema["mainEntity"]["@type"] == "Person", "profile types incorrect")
person = schema["mainEntity"]
require(person["image"] == ORIGIN + "/assets/portrait.jpeg", "profile portrait mismatch")
visible = " ".join("".join(pages["index.html"].text).split())
require(person["name"] in visible and person["jobTitle"].casefold() in visible.casefold(), "schema identity not visible")
require(person["description"] in visible, "schema bio not visible")
home_hrefs = {a.get("href") for tag, a in pages["index.html"].tags if tag == "a"}
require(set(person["sameAs"]) <= home_hrefs, "hidden social identity in schema")
markdown = (SITE / "about.md").read_text().strip()
require(markdown.startswith("# Alex Roan") and "<p>" not in markdown, "Markdown converted to HTML")
require(person["description"] in markdown, "plain-text bio differs")
require(all(url in markdown for url in person["sameAs"]), "plain-text social profile missing")
for name in ("llms.txt", "robots.txt", "sitemap.xml", "about.md", "profile.json"):
    require("{{" not in (SITE / name).read_text(), f"unrendered Liquid in {name}")
require("User-agent: *\nAllow: /" in (SITE / "robots.txt").read_text(), "crawler access blocked")
require(f"Sitemap: {ORIGIN}/sitemap.xml" in (SITE / "robots.txt").read_text(), "sitemap discovery missing")
xml = ElementTree.parse(SITE / "sitemap.xml")
require([e.text for e in xml.findall(".//{*}loc")] == [ORIGIN + "/"], "sitemap URL set incorrect")
png = (SITE / "assets/social-card.png").read_bytes()
require(png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (1200, 630), "social card dimensions incorrect")
css = (SITE / "assets/style.css").read_text()
require("@import" not in css and "url(" not in css, "unexpected CSS resource")
require(sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) < 350_000, "static site size budget exceeded")
print(f"PASS: {len(actual)} published files; links, metadata, schema, text parity, crawler access and static security checks.")
