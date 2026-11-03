"""Test intent: accept only explicitly qualified public-page identity claims.

- Visible rel=me links and directly qualified Person nodes keep source indices/pointers.
- Person authors, commenters, nested mentions, and shared names stay excluded.
- Unsafe URLs and malformed JSON-LD are refused without losing visible links.
- Bounded parsing never executes scripts or reads hidden/template/noscript rel=me.
"""

import json

from src.enrichment.public_page_claims import extract_public_page_claims


PAGE = "https://example.test/people/alice"


def test_anonymous_graph_page_cannot_assign_a_different_documents_person():
    person={'@type':'Person','name':'Other page subject'}
    graph={'@graph':[{'@type':'ProfilePage','mainEntity':person}]}
    markup=lambda data:'<script type="application/ld+json">'+json.dumps(data)+'</script>'
    assert extract_public_page_claims(markup(graph),PAGE)['people']==[]
    # The root document itself explicitly declares its main subject.
    root={'@type':'ProfilePage','mainEntity':person}
    claims=extract_public_page_claims(markup(root),PAGE)['people']
    assert claims[0]['name']['value']=='Other page subject'


def test_visible_rel_me_and_explicit_profile_page_person_keep_source_claims():
    payload = {
        "@graph": [
            {"@type": "ProfilePage", "url": PAGE, "mainEntity": {"@id": "#alice"}},
            {"@id": "#alice", "@type": "Person", "name": "Alice Example",
             "url": PAGE, "sameAs": ["https://social.example/alice#profile", "javascript:bad()"],
             "jobTitle": ["Researcher", "Writer", 5],
             "worksFor": {"@id": "#lab"},
             "affiliation": {"@type": "CollegeOrUniversity", "name": "North College"},
             "alumniOf": {"@type": "Organization", "name": "Former Institute"}},
            {"@id": "#lab", "@type": "Organization", "name": "Example Lab",
             "url": "https://lab.example/"},
        ]
    }
    html = '''<a href="https://social.example/alice" rel="me">Alice <b>on social</b></a>
        <link rel="alternate me" href="https://fed.example/@alice" title="Fediverse">
        <script type="application/ld+json">''' + json.dumps(payload) + "</script>"
    result = extract_public_page_claims(html, PAGE + "#top")

    assert [item["url"] for item in result["selfLinks"]] == [
        "https://social.example/alice", "https://fed.example/@alice"]
    assert result["selfLinks"][0]["label"] == "Alice on social"
    assert result["selfLinks"][0]["sourceIndex"] == 0
    assert result["selfLinks"][1]["sourceIndex"] == 1
    assert len(result["people"]) == 1
    person = result["people"][0]
    assert person["name"]["value"] == "Alice Example"
    assert person["name"]["pointer"] == "/@graph/1/name"
    assert person["sourceIndex"] == 0
    assert person["sameAs"] == [{"url": "https://social.example/alice#profile",
                                  "sourceIndex": 0, "pointer": "/@graph/1/sameAs/0"}]
    assert [claim["value"] for claim in person["jobTitle"]] == ["Researcher", "Writer"]
    assert person["worksFor"][0]["name"] == "Example Lab"
    assert person["worksFor"][0]["pointer"] == "/@graph/1/worksFor"
    assert person["worksFor"][0]["resolvedPointer"] == "/@graph/2"
    assert person["worksFor"][0]["urlPointer"] == "/@graph/2/url"
    assert person["affiliation"][0]["namePointer"] == "/@graph/1/affiliation/name"
    assert person["alumniOf"][0]["name"] == "Former Institute"
    assert "not verified identity" in result["boundary"]
    assert "Email" in result["boundary"]


def test_top_level_person_requires_exact_normalized_page_url_not_domain_or_name():
    entries = [
        {"@type": "Person", "name": "Alice Example", "url": "https://example.test/people/bob"},
        {"@type": "Person", "name": "Alice Example", "url": "https://example.test/"},
        {"@type": "Person", "name": "Alice Example", "url": PAGE},
        {"@type": "https://evil.test/Person", "name": "Alice Example", "url": PAGE},
    ]
    result = extract_public_page_claims(
        '<script type="application/ld+json">' + json.dumps(entries) + '</script>', PAGE)
    assert [p["name"]["value"] for p in result["people"]] == ["Alice Example"]
    assert result["people"][0]["pointer"] == "/2"
    root_person = extract_public_page_claims(
        '<script type="application/ld+json">' +
        json.dumps({"@type": "Person", "name": "Alice", "url": PAGE}) + '</script>', PAGE)
    assert root_person["people"][0]["pointer"] == ""


def test_article_authors_commenters_and_arbitrary_nested_people_are_not_page_subjects():
    data = {
        "@type": "WebPage", "mainEntity": {"@type": "Article", "author": {
            "@type": "Person", "name": "Article Author", "url": PAGE}},
        "comment": {"@type": "Comment", "author": {
            "@type": "Person", "name": "Commenter", "url": PAGE}},
        "mentions": [{"@type": "Person", "name": "Mentioned", "url": PAGE}],
    }
    result = extract_public_page_claims(
        '<script type="application/ld+json">' + json.dumps(data) + '</script>', PAGE)
    assert result["people"] == []


def test_mismatched_page_entity_and_hidden_jsonld_are_not_page_subjects():
    hidden_person = {"@type": "Person", "name": "Hidden", "url": PAGE}
    wrong_page = {"@type": "WebPage", "url": "https://example.test/other",
                  "mainEntity": {"@type": "Person", "name": "Other Page", "url": PAGE}}
    html = ('<template><script type="application/ld+json">' + json.dumps(hidden_person) +
            '</script></template><div hidden><script type="application/ld+json">' +
            json.dumps(hidden_person) + '</script></div><script type="application/ld+json">' +
            json.dumps(wrong_page) + '</script>')
    assert extract_public_page_claims(html, PAGE)["people"] == []


def test_hidden_jsonld_keeps_original_script_ordinal_without_reading_its_claims():
    hidden = {"@type": "Person", "name": "Hidden", "url": PAGE}
    visible = {"@type": "Person", "name": "Visible", "url": PAGE}
    html = ('<template><script type="application/ld+json">' + json.dumps(hidden) +
            '</script></template><script type="application/ld+json">' +
            json.dumps(visible) + '</script>')
    result = extract_public_page_claims(html, PAGE)
    assert len(result["people"]) == 1
    assert result["people"][0]["name"]["value"] == "Visible"
    assert result["people"][0]["sourceIndex"] == 1


def test_unsafe_claim_urls_are_rejected_and_bad_json_does_not_erase_rel_me():
    html = '''<a rel="me" href="javascript:alert(1)">bad</a>
        <a rel="me" href="https://user:secret@example.test/profile">bad</a>
        <a rel="me" href="//social.example/alice">ok</a>
        <script type="application/ld+json">{"@type":</script>'''
    result = extract_public_page_claims(html, PAGE)
    assert [link["url"] for link in result["selfLinks"]] == ["https://social.example/alice"]
    assert result["people"] == []
    assert result["metadataWarnings"][0]["kind"] == "malformed_jsonld"


def test_hidden_scripts_templates_and_noscript_are_not_scanned_or_executed():
    html = '''<template><a rel="me" href="https://hidden.example/">Hidden</a></template>
        <noscript><a rel="me" href="https://noscript.example/">No script</a></noscript>
        <div hidden><a rel="me" href="https://hidden-attr.example/">Hidden attr</a></div>
        <div aria-hidden="true"><a rel="me" href="https://aria.example/">ARIA hidden</a></div>
        <script>window.called = true</script>
        <a rel="me" href="/visible#profile">Visible</a>'''
    result = extract_public_page_claims(html, PAGE)
    assert [link["url"] for link in result["selfLinks"]] == ["https://example.test/visible#profile"]
    assert result["people"] == []


def test_nested_organization_person_is_not_reported_as_an_organization():
    data = {"@type": "ProfilePage", "mainEntity": {
        "@type": "Person", "name": "Alice", "worksFor": {
            "@type": "Person", "name": "A different person", "url": "https://example.test/"}}}
    result = extract_public_page_claims(
        '<script type="application/ld+json">' + json.dumps(data) + '</script>', PAGE)
    assert result["people"][0]["worksFor"] == []


def test_untyped_organization_property_is_retained_but_explicit_person_is_rejected():
    data = {"@type": "ProfilePage", "mainEntity": {
        "@type": "Person", "name": "Alice",
        "worksFor": {"name": "Named Studio", "url": "https://studio.example/"},
        "affiliation": {"@type": "Person", "name": "Not an org", "url": "https://person.example/"},
        "alumniOf": {"@type": "NewsMediaOrganization", "name": "Daily Source"},
    }}
    result = extract_public_page_claims(
        '<script type="application/ld+json">' + json.dumps(data) + '</script>', PAGE)
    person = result["people"][0]
    assert person["worksFor"][0]["name"] == "Named Studio"
    assert person["worksFor"][0]["url"] == "https://studio.example/"
    assert person["affiliation"] == []
    assert person["alumniOf"][0]["name"] == "Daily Source"


def test_limits_bound_scripts_nodes_and_warning_count():
    from src.enrichment.public_page_claims import MAX_FIELD_ITEMS, MAX_GRAPH_NODES, MAX_SCRIPT_CHARS

    oversized = "x" * (MAX_SCRIPT_CHARS + 1)
    result = extract_public_page_claims(
        '<script type="application/ld+json">' + oversized + '</script>', PAGE)
    assert result["people"] == []
    assert result["metadataWarnings"][0]["kind"] == "script_truncated"

    graph = [{"@type": "Person", "name": "Alice", "url": PAGE,
              **({"sameAs": [f"https://social.example/{i}" for i in range(80)]} if i == 0 else {})}
             for i in range(MAX_GRAPH_NODES + 10)]
    bounded = extract_public_page_claims(
        '<script type="application/ld+json">' + json.dumps({"@graph": graph}) + '</script>', PAGE)
    assert len(bounded["people"]) <= MAX_GRAPH_NODES
    assert len(bounded["people"][0]["sameAs"]) == MAX_FIELD_ITEMS
    assert any(w["kind"] == "nodes_truncated" for w in bounded["metadataWarnings"])
    assert len(result["metadataWarnings"]) <= 23
