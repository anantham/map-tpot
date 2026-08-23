"""Behavioural tests for bio-link feature extraction and site classification.

Test Intent
-----------
* A personal site and a company site must land in different buckets — that
  distinction is the whole reason the classifier exists.
* Outbound identity links (GitHub, arXiv, Substack) must survive extraction,
  because they are the evidence the X follow graph structurally cannot contain.
* Relative URLs must be resolved against the page, or images and links are
  unusable downstream.
* Parked/empty pages must be marked non-reviewable so they never reach a human.
* An ambiguous page must return ``unknown`` rather than a confident guess; a
  measurable abstention beats an untrustworthy label.

Fixtures are realistic whole pages, not minimal stubs, so the tests survive
internal refactors of the regex layer.
"""
from __future__ import annotations

import pytest

from src.enrichment import (
    classify, extract, platform_for, redirect_target, urls_in_text,
)

PERSONAL = """<!doctype html><html><head>
<title>Ada Lovelace</title>
<meta property="og:description" content="Notes on analytical engines.">
<meta property="og:image" content="/static/me.jpg">
<link rel="alternate" type="application/rss+xml" href="/feed.xml">
</head><body>
<nav><a href="/about">About</a><a href="/blog">Blog</a><a href="/now">Now</a></nav>
<h1>Hi, I'm Ada</h1>
<p>About me: I write about computation and I build small tools.
My work lives mostly in the open.</p>
<img src="images/desk.png"><img src="https://cdn.example.com/x.png">
<a href="https://github.com/adalovelace">GitHub</a>
<a href="https://adalovelace.substack.com">Newsletter</a>
<a href="https://arxiv.org/a/lovelace_a_1">arXiv</a>
</body></html>"""

COMPANY = """<!doctype html><html><head><title>Nimbus | Ship faster</title>
<meta name="description" content="Nimbus is the platform for modern teams.">
</head><body>
<nav><a href="/pricing">Pricing</a><a href="/careers">Careers</a></nav>
<h1>We build infrastructure for modern teams</h1>
<p>Our mission is to help engineering organisations ship faster.
Trusted by hundreds of teams. Book a demo to talk to our team.</p>
<footer>© 2026 Nimbus Inc. All rights reserved. Privacy policy · Terms of service</footer>
</body></html>"""

PARKED = """<html><head><title>example.com</title></head>
<body><p>This domain is for sale.</p></body></html>"""

AMBIGUOUS = """<html><head><title>hello</title></head>
<body><p>a page that exists and says very little at all, but does have
enough characters in it to clear the emptiness floor comfortably.</p>
<img src="/a.png"></body></html>"""


class TestExtraction:
    def test_resolves_relative_image_and_prefers_og_image_first(self):
        f = extract(PERSONAL, "https://ada.example/")
        assert f.og_image == "https://ada.example/static/me.jpg"
        assert f.images[0] == f.og_image, "og:image should lead the image list"
        assert "https://ada.example/images/desk.png" in f.images

    def test_separates_internal_paths_from_outbound_links(self):
        f = extract(PERSONAL, "https://ada.example/")
        assert "/about" in f.internal_paths and "/blog" in f.internal_paths
        assert all("ada.example" not in u for u in f.outbound)

    def test_identity_links_are_singled_out(self):
        f = extract(PERSONAL, "https://ada.example/")
        hosts = {u.split("/")[2] for u in f.signal_links}
        assert {"github.com", "arxiv.org"} <= hosts

    def test_title_falls_back_to_title_tag_when_no_og_title(self):
        assert extract(PERSONAL, "https://ada.example/").title == "Ada Lovelace"

    def test_feed_discovery(self):
        assert extract(PERSONAL, "https://ada.example/").feed_urls == (
            "https://ada.example/feed.xml",)

    def test_visible_text_drops_markup_and_scripts(self):
        f = extract(
            "<html><body><script>var x=1;</script><p>Real  copy</p></body></html>",
            "https://x.example/")
        assert "var x" not in f.text
        assert "Real copy" in f.text

    def test_malformed_markup_does_not_raise(self):
        f = extract("<html><body><p>unclosed <a href=", "https://x.example/")
        assert isinstance(f.text, str)

    @pytest.mark.parametrize("href", [
        "http://[unbalanced/path",          # crashed a real 230-page run at #119
        "https://[::1",
        "//[bad]]/x",
        "http://[]",
    ])
    def test_hostile_href_is_skipped_not_raised(self, href):
        """urlsplit raises ValueError('Invalid IPv6 URL') on unbalanced brackets.

        Regression: pages in the wild carry these, and one killed a full batch
        mid-run. A bad href must be dropped, never propagated as an exception.
        """
        html = f'<html><body><a href="{href}">x</a><img src="{href}"><p>body copy here</p></body></html>'
        f = extract(html, "https://x.example/")
        assert "body copy here" in f.text
        assert all(u for u in f.outbound), "no empty URLs should survive"

    def test_hostile_page_url_does_not_raise(self):
        assert extract("<html><body>hi</body></html>", "http://[bad").text == "hi"

    @pytest.mark.parametrize("url,expected", [
        ("https://ada.github.io/notes", "personal"),
        ("https://someone.substack.com/", "newsletter"),
        ("https://linktr.ee/someone", "aggregator"),
        ("https://github.com/ada", "code"),
        ("https://example.com/", None),
    ])
    def test_platform_detection(self, url, expected):
        assert platform_for(url) == expected


class TestClassification:
    def test_personal_site_is_not_company(self):
        v = classify(extract(PERSONAL, "https://ada.example/"))
        assert v.site_type in {"personal", "blog"}
        assert v.scores.get("company", 0) < v.scores[v.site_type]
        assert v.person_signal > 0.3
        assert v.is_reviewable

    def test_company_site_is_classified_as_company(self):
        v = classify(extract(COMPANY, "https://nimbus.example/"))
        assert v.site_type == "company"
        assert v.person_signal < 0.3

    def test_parked_domain_is_dead_and_not_reviewable(self):
        v = classify(extract(PARKED, "https://example.com/"))
        assert v.site_type == "dead"
        assert not v.is_reviewable, "parked pages must never reach a human"

    def test_ambiguous_page_abstains_rather_than_guessing(self):
        v = classify(extract(AMBIGUOUS, "https://x.example/"))
        assert v.site_type == "unknown"
        assert v.confidence == 0.0

    def test_verdict_always_explains_itself(self):
        for html, url in ((PERSONAL, "https://ada.example/"),
                          (COMPANY, "https://nimbus.example/"),
                          (PARKED, "https://example.com/")):
            v = classify(extract(html, url))
            assert v.reasons, f"{url} produced a verdict with no reasons"

    def test_confidence_is_bounded(self):
        for html, url in ((PERSONAL, "https://ada.example/"),
                          (COMPANY, "https://nimbus.example/")):
            v = classify(extract(html, url))
            assert 0.0 <= v.confidence <= 0.95


class TestBioUrlMining:
    """Bios carry the link more often than the website column does."""

    def test_plain_url_is_found(self):
        assert urls_in_text("writer. https://ada.example/ she/her") == (
            "https://ada.example/",)

    def test_trailing_sentence_punctuation_is_stripped(self):
        assert urls_in_text("see https://ada.example/notes.") == (
            "https://ada.example/notes",)

    def test_unbalanced_closing_paren_is_stripped(self):
        assert urls_in_text("(see https://ada.example/x)") == ("https://ada.example/x",)

    def test_balanced_parens_inside_path_survive(self):
        assert urls_in_text("https://en.wikipedia.org/wiki/Ada_(name)") == (
            "https://en.wikipedia.org/wiki/Ada_(name)",)

    def test_twitter_self_links_are_not_evidence(self):
        assert urls_in_text("me https://twitter.com/ada and https://x.com/ada") == ()

    def test_multiple_urls_deduplicated_and_ordered(self):
        got = urls_in_text("https://a.example https://b.example https://a.example")
        assert got == ("https://a.example", "https://b.example")

    def test_limit_is_respected(self):
        text = " ".join(f"https://s{i}.example" for i in range(10))
        assert len(urls_in_text(text, limit=3)) == 3

    def test_empty_and_none_are_safe(self):
        assert urls_in_text(None) == ()
        assert urls_in_text("no links here at all") == ()

    def test_hostile_url_in_text_does_not_raise(self):
        assert urls_in_text("http://[bad and https://ok.example") == (
            "https://ok.example",)


class TestRedirectInterstitials:
    """t.co answers browsers with a JS interstitial, not an HTTP 301.

    Reading it resolves the destination without contacting that destination, so
    dead and hostile targets still yield the URL the account pointed at.
    """

    TCO = ('<head><meta name="referrer" content="always"><noscript>'
           '<META http-equiv="refresh" content="0;URL=http://langsec.org"></noscript>'
           '<title>http://langsec.org</title></head>'
           '<script>window.opener = null; location.replace("http:\\/\\/langsec.org")'
           '</script>')

    def test_real_tco_interstitial_resolves(self):
        assert redirect_target(self.TCO) == "http://langsec.org"

    def test_escaped_slashes_are_unescaped(self):
        assert "\\/" not in (redirect_target(self.TCO) or "")

    def test_js_location_replace_alone_is_enough(self):
        assert redirect_target('<script>location.replace("https://x.example/a")</script>'
                               ) == "https://x.example/a"

    def test_window_location_assignment(self):
        assert redirect_target('<script>window.location = "https://x.example/b"</script>'
                               ) == "https://x.example/b"

    def test_relative_target_resolves_against_base(self):
        got = redirect_target('<meta http-equiv="refresh" content="0;url=/landing">',
                              base="https://short.example/abc")
        assert got == "https://short.example/landing"

    def test_ordinary_page_is_not_treated_as_a_redirect(self):
        """A real page must never be mistaken for an interstitial."""
        page = "<html><body>" + ("real content " * 900) + "</body></html>"
        assert redirect_target(page) is None

    def test_page_with_no_redirect_returns_none(self):
        assert redirect_target("<html><head><title>hi</title></head></html>") is None

    def test_empty_input_is_safe(self):
        assert redirect_target("") is None

    def test_hostile_target_is_rejected(self):
        assert redirect_target(
            '<meta http-equiv="refresh" content="0;url=http://[bad">') is None


class TestHtmlEntityDecoding:
    """URLs in attributes arrive escaped; leaving them so silently corrupts them.

    Regression: 201 stored rows had image URLs containing a literal "&amp;" and
    23 had corrupted identity links, which then failed to fetch for no real
    reason. Found when a vision probe could not download an Unsplash og:image.
    """

    def test_ampersand_in_query_string_is_decoded(self):
        f = extract('<html><body><img src="https://i.example/p.jpg?a=1&amp;b=2">'
                    '</body></html>', "https://x.example/")
        assert f.images == ("https://i.example/p.jpg?a=1&b=2",)

    def test_og_image_query_is_decoded(self):
        f = extract('<meta property="og:image" '
                    'content="https://i.example/x.jpg?w=1&amp;h=2">',
                    "https://x.example/")
        assert f.og_image == "https://i.example/x.jpg?w=1&h=2"

    def test_identity_link_query_is_decoded(self):
        f = extract('<a href="https://github.com/a?tab=repos&amp;type=all">gh</a>',
                    "https://x.example/")
        assert f.signal_links == ("https://github.com/a?tab=repos&type=all",)

    def test_entities_in_bio_text_are_decoded(self):
        assert urls_in_text("me https://s.example/?a=1&amp;b=2") == (
            "https://s.example/?a=1&b=2",)

    def test_redirect_target_entities_are_decoded(self):
        assert redirect_target(
            '<meta http-equiv="refresh" content="0;url=https://d.example/?a=1&amp;b=2">'
        ) == "https://d.example/?a=1&b=2"


class TestVisionConsensus:
    """Independent agreement is the signal; self-reported confidence is not."""

    @staticmethod
    def v(model, suggests, caption="a thing", conf=0.8, error=None):
        from src.enrichment import ImageVerdict
        return ImageVerdict(caption, "logo", False, "", suggests, conf, model, error)

    def test_unanimous_is_trustworthy(self):
        from src.enrichment import consensus
        c = consensus([self.v("a", "personal"), self.v("b", "personal")])
        assert c.agreement == "unanimous" and c.suggests == "personal"
        assert c.is_trustworthy

    def test_split_is_not_trustworthy_and_names_the_disagreement(self):
        from src.enrichment import consensus
        c = consensus([self.v("a", "personal"), self.v("b", "company")])
        assert c.agreement == "split" and c.suggests == "unclear"
        assert not c.is_trustworthy
        assert "a=personal" in c.note and "b=company" in c.note

    def test_single_voter_is_weak_not_trusted(self):
        from src.enrichment import consensus
        c = consensus([self.v("a", "personal"), self.v("b", "x", error="boom")])
        assert c.agreement == "single" and not c.is_trustworthy

    def test_confident_empty_caption_never_votes(self):
        """gemma4 returned confidence 1.0 with an empty caption; it must not count."""
        from src.enrichment import consensus
        c = consensus([self.v("a", "company", caption="", conf=1.0),
                       self.v("b", "company", caption="", conf=1.0)])
        assert c.agreement == "none" and not c.is_trustworthy

    def test_no_verdicts_at_all(self):
        from src.enrichment import consensus
        assert consensus([]).agreement == "none"
