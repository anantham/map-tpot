import json
from urllib.parse import urljoin, urlsplit, urlunsplit

from src.enrichment.page_claim_markup import capture_jsonld_scripts, capture_rel_me_links

MAX_HTML_CHARS = 1_000_000
MAX_JSON_SCRIPTS = 20
MAX_SCRIPT_CHARS = 100_000
MAX_GRAPH_NODES = 200
MAX_FIELD_ITEMS = 30
MAX_STRING_CHARS = 500
MAX_SELF_LINKS = 100

_ORG_TYPES = {"Organization", "Corporation", "EducationalOrganization", "CollegeOrUniversity",
              "School", "GovernmentOrganization", "NGO", "SportsOrganization", "LocalBusiness"}


def _organization_type_allowed(node):
    types = _types(node)
    return not types or all(item in _ORG_TYPES or item.endswith("Organization") for item in types)


def _safe_http(value, base_url):
    if not isinstance(value, str) or not value.strip(): return None
    value = value.strip()
    if any(ord(char) < 32 for char in value): return None
    try:
        parts = urlsplit(urljoin(base_url, value))
        if (parts.scheme.lower() not in {"http", "https"} or not parts.hostname
                or parts.username is not None or parts.password is not None): return None
        port = parts.port
        host = parts.hostname.lower()
        if ":" in host and not host.startswith("["): host = f"[{host}]"
        netloc = host if port is None or (parts.scheme.lower(), port) in {("http", 80), ("https", 443)} else f"{host}:{port}"
        return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, parts.fragment))
    except (TypeError, ValueError): return None


def _pointer(path):
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in path) if path else ""


def _short_string(value):
    if isinstance(value, str) and value.strip(): return value.strip()[:MAX_STRING_CHARS]
    return None


def _types(node):
    value = node.get("@type") if isinstance(node, dict) else None
    values = value if isinstance(value, list) else [value]
    return {item.rsplit("/", 1)[-1] for item in values if isinstance(item, str) and
            ((":" not in item and "/" not in item and "#" not in item) or
             item.startswith(("http://schema.org/", "https://schema.org/")))}


def _nodes(document):
    roots = document if isinstance(document, list) else [document]
    nodes = []
    for root_index, root in enumerate(roots[:MAX_GRAPH_NODES]):
        if not isinstance(root, dict): continue
        nodes.append((root, [root_index] if isinstance(document, list) else []))
        graph = root.get("@graph")
        if isinstance(graph, list):
            for graph_index, node in enumerate(graph[:MAX_GRAPH_NODES - len(nodes)]):
                if isinstance(node, dict): nodes.append((node, ([root_index, "@graph", graph_index] if isinstance(document, list) else ["@graph", graph_index])))
    return nodes


def _url_values(value, base_url):
    values = value if isinstance(value, list) else [value]
    for item in values[:MAX_FIELD_ITEMS]:
        url = _safe_http(item.get("@id") if isinstance(item, dict) else item, base_url)
        if url: yield url


def _page_match(value, base_url, page_url):
    return any(urlsplit(url)._replace(fragment="").geturl() == page_url
               for url in _url_values(value, base_url))


def _page_node_matches(node, base_url, page_url, path):
    identifiers = [node[field] for field in ('url','@id') if field in node]
    # An anonymous top-level page describes this document. An unanchored page
    # inside @graph could describe a different document and must not qualify it.
    return (bool(identifiers) or '@graph' not in path) and all(
        _page_match(value,base_url,page_url) for value in identifiers)


def _person_claim(node, path, script_index, base_url, by_id):
    result = {"sourceIndex": script_index, "pointer": _pointer(path)}
    name = _short_string(node.get("name"))
    if name:
        result["name"] = {"value": name, "sourceIndex": script_index,
                          "pointer": _pointer(path + ["name"])}

    same_as = []
    value = node.get("sameAs")
    items = value if isinstance(value, list) else [value]
    for index, item in enumerate(items[:MAX_FIELD_ITEMS]):
        url = _safe_http(item.get("@id") if isinstance(item, dict) else item, base_url)
        if url:
            same_as.append({"url": url, "sourceIndex": script_index,
                            "pointer": _pointer(path + ["sameAs"] + ([index] if isinstance(value, list) else []))})
    result["sameAs"] = same_as
    titles = []
    value = node.get("jobTitle")
    items = value if isinstance(value, list) else [value]
    for index, item in enumerate(items[:MAX_FIELD_ITEMS]):
        title = _short_string(item)
        if title: titles.append({"value": title, "sourceIndex": script_index, "pointer": _pointer(path + ["jobTitle"] + ([index] if isinstance(value, list) else []))})
    result["jobTitle"] = titles
    organization_claims = {}
    for field in ("worksFor", "affiliation", "alumniOf"):
        found = []
        values = node.get(field)
        values = values if isinstance(values, list) else [values]
        for index, org in enumerate(values[:MAX_FIELD_ITEMS]):
            source_path = path + [field] + ([index] if isinstance(node.get(field), list) else [])
            resolved = by_id.get(org.get("@id")) if isinstance(org, dict) and isinstance(org.get("@id"), str) else None
            org, org_path = resolved if resolved else (org, source_path)
            if not isinstance(org, dict) or not _organization_type_allowed(org): continue
            item = {"sourceIndex": script_index, "pointer": _pointer(source_path),
                    "resolvedPointer": _pointer(org_path)}
            org_name = _short_string(org.get("name"))
            if org_name:
                item["name"] = org_name
                item["namePointer"] = _pointer(org_path + ["name"])
            raw_url = org.get("url", org.get("@id"))
            if isinstance(raw_url, dict): raw_url = raw_url.get("@id")
            org_url = _safe_http(raw_url, base_url)
            if org_url:
                item["url"] = org_url
                item["urlPointer"] = _pointer(org_path +
                    (["url"] if "url" in org else ["@id"]))
            if org_name or org_url:
                found.append(item)
        organization_claims[field] = found
    result.update(organization_claims)
    return result


def extract_public_page_claims(html, base_url):
    """Extract rel=me links and explicitly qualified JSON-LD page subjects.

    All values are publisher claims, not verified identity or current employment.
    No script is executed, no network is accessed, and contact details are ignored.
    """
    html = html if isinstance(html, str) else ""
    warnings = []
    if len(html) > MAX_HTML_CHARS:
        html = html[:MAX_HTML_CHARS]
        warnings.append({"kind": "html_truncated", "message": "HTML input limit reached."})
    page_url = _safe_http(base_url, base_url)
    page_url = urlsplit(page_url)._replace(fragment="").geturl() if page_url else ""

    links = capture_rel_me_links(html, page_url, _safe_http, MAX_STRING_CHARS)
    self_links = links[:MAX_SELF_LINKS]
    if len(links) > MAX_SELF_LINKS:
        warnings.append({"kind": "self_links_truncated", "message": "rel=me link limit reached."})

    people = []
    seen_people = set()
    scripts = capture_jsonld_scripts(html, MAX_JSON_SCRIPTS)
    if len(scripts) > MAX_JSON_SCRIPTS:
        warnings.append({"kind": "scripts_truncated", "message": "JSON-LD script limit reached."})
    for script_index, raw in scripts[:MAX_JSON_SCRIPTS]:
        if raw is None: continue
        if len(raw) > MAX_SCRIPT_CHARS:
            warnings.append({"kind": "script_truncated", "scriptIndex": script_index, "message": "JSON-LD script size limit reached."})
            continue
        try:
            document = json.loads(raw)
        except (json.JSONDecodeError, RecursionError):
            warnings.append({"kind": "malformed_jsonld", "scriptIndex": script_index, "message": "JSON-LD could not be parsed."})
            continue
        nodes = _nodes(document)
        if len(nodes) >= MAX_GRAPH_NODES:
            warnings.append({"kind": "nodes_truncated", "scriptIndex": script_index, "message": "JSON-LD graph node limit reached."})
        by_id = {node.get("@id"): (node, path) for node, path in nodes
                 if isinstance(node.get("@id"), str)}

        selected = []
        for node, path in nodes:
            if not (_types(node) & {"WebPage", "ProfilePage"}) or not _page_node_matches(node, page_url, page_url, path):
                continue
            main = node.get("mainEntity")
            entities = main if isinstance(main, list) else [main]
            for index, entity in enumerate(entities[:MAX_FIELD_ITEMS]):
                entity_path = path + ["mainEntity"] + ([index] if isinstance(main, list) else [])
                if isinstance(entity, dict) and isinstance(entity.get("@id"), str):
                    resolved = by_id.get(entity["@id"])
                    if resolved:
                        entity, entity_path = resolved
                if isinstance(entity, dict) and "Person" in _types(entity):
                    selected.append((entity, entity_path))

        for node, path in nodes:
            if "Person" not in _types(node):
                continue
            own_url = node.get("url")
            own_id = node.get("@id")
            if _page_match(own_url, page_url, page_url) or _page_match(own_id, page_url, page_url):
                selected.append((node, path))

        for person, path in selected[:MAX_GRAPH_NODES]:
            key = (script_index, tuple(path))
            if key in seen_people:
                continue
            seen_people.add(key)
            people.append(_person_claim(person, path, script_index, page_url, by_id))

    return {
        "selfLinks": self_links,
        "people": people,
        "metadataWarnings": warnings[:MAX_JSON_SCRIPTS + 3],
        "boundary": (
            "rel=me and JSON-LD are publisher assertions, not verified identity. "
            "worksFor is a reported association; alumniOf is not necessarily employment. "
            "No current/past status or dates are inferred. Email and phone fields are excluded."
        ),
    }
