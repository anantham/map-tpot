"""Bounded HTML markup capture used by public-page claim extraction."""

from html.parser import HTMLParser


_HIDDEN_TAGS = {"template", "noscript"}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
              "meta", "param", "source", "track", "wbr"}


class _RelMeParser(HTMLParser):
    """Collect visible rel=me anchors and links while preserving tag ordinals."""

    def __init__(self, base_url, safe_http, max_string_chars):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.safe_http = safe_http
        self.max_string_chars = max_string_chars
        self.stack = []
        self.hidden_depth = 0
        self.element_index = 0
        self.anchor = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (tag in _HIDDEN_TAGS or "hidden" in attrs
                  or str(attrs.get("aria-hidden", "")).lower() == "true")
        if tag not in _VOID_TAGS:
            self.stack.append((tag, hidden))
            self.hidden_depth += int(hidden)
        if tag not in {"a", "link"}:
            return
        index = self.element_index
        self.element_index += 1
        if self.hidden_depth or hidden:
            return
        if "me" not in str(attrs.get("rel", "")).lower().split():
            return
        url = self.safe_http(attrs.get("href"), self.base_url)
        if not url:
            return
        label = (attrs.get("aria-label") or attrs.get("title") or "").strip()
        if tag == "a":
            self.anchor = {"index": index, "url": url, "labelParts": [], "fallback": label}
        else:
            self.links.append({"url": url, "label": label or url,
                               "sourceIndex": index, "sourceType": tag})

    def handle_data(self, data):
        if self.anchor is not None and not self.hidden_depth:
            self.anchor["labelParts"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            label = " ".join(" ".join(self.anchor["labelParts"]).split())
            self.links.append({"url": self.anchor["url"],
                               "label": (label or self.anchor["fallback"] or self.anchor["url"])
                                        [:self.max_string_chars],
                               "sourceIndex": self.anchor["index"], "sourceType": "a"})
            self.anchor = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                if any(hidden for _, hidden in self.stack[index + 1:]):
                    return
                self.hidden_depth -= sum(int(hidden) for _, hidden in self.stack[index:])
                del self.stack[index:]
                break


def capture_rel_me_links(html, base_url, safe_http, max_string_chars):
    parser = _RelMeParser(base_url, safe_http, max_string_chars)
    parser.feed(html)
    parser.close()
    if parser.anchor is not None:
        parser.handle_endtag("a")
    return parser.links


class _JsonLdParser(HTMLParser):
    """Capture visible JSON-LD scripts, retaining original script ordinals."""

    def __init__(self, max_scripts):
        super().__init__(convert_charrefs=True)
        self.max_scripts = max_scripts
        self.items = []
        self.current = None
        self.script_index = None
        self.count = 0
        self.stack = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        hidden = (tag in _HIDDEN_TAGS or "hidden" in attrs
                  or str(attrs.get("aria-hidden", "")).lower() == "true")
        if tag not in _VOID_TAGS:
            self.stack.append((tag, hidden))
            self.hidden_depth += int(hidden)
        if (tag == "script" and self.script_index is None
                and attrs.get("type", "").split(";", 1)[0].strip().lower() == "application/ld+json"):
            self.script_index = self.count
            self.count += 1
            self.current = [] if self.count <= self.max_scripts and not self.hidden_depth else None

    def handle_data(self, data):
        if self.script_index is not None and self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.script_index is not None:
            payload = "".join(self.current) if self.current is not None else None
            self.items.append((self.script_index, payload))
            self.script_index, self.current = None, None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                if any(hidden for _, hidden in self.stack[index + 1:]):
                    return
                self.hidden_depth -= sum(int(hidden) for _, hidden in self.stack[index:])
                del self.stack[index:]
                break


def capture_jsonld_scripts(html, max_scripts):
    parser = _JsonLdParser(max_scripts)
    parser.feed(html)
    parser.close()
    if parser.script_index is not None:
        payload = "".join(parser.current) if parser.current is not None else None
        parser.items.append((parser.script_index, payload))
    return parser.items
