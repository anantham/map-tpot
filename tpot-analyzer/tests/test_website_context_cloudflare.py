"""Test intent:

- Decode only strict Cloudflare XOR email inputs and preserve exact source metadata.
- Keep href and data-attribute occurrences distinct, even for the same address.
- Exclude malformed provider endpoints from general links and suppress hidden markup.
- Stamp newly described cache pages with the parser generation that emits this schema.
"""
import gzip

import src.enrichment.website_context as website_context
from src.data.cached_websites import describe_cached_page


def _encoded(address, key=0x5A):
    return (bytes([key]) + bytes(byte ^ key for byte in address.encode('utf-8'))).hex()


def test_public_extractor_keeps_each_cloudflare_input_with_source_provenance():
    href = '/cdn-cgi/l/email-protection#' + _encoded('hello@example.test')
    data = _encoded('hello@example.test')
    html = (f'<a href="{href}">Public inbox</a>\n'
            f'<span class="badge __cf_email__" data-cfemail="{data}">Team email</span>')
    page = website_context.extract_website_context(html, 'https://publisher.example.test/')

    clues = [item for item in page['emailClues'] if item['kind'] == 'cloudflare_decoded']
    assert [item['address'] for item in clues] == ['hello@example.test', 'hello@example.test']
    assert [item['label'] for item in clues] == ['Public inbox', 'Team email']
    assert [item['decoding'] for item in clues] == [
        {'method':'cloudflare-xor-v1','attribute':'href','value':href,
         'tag':'a','line':1,'column':0},
        {'method':'cloudflare-xor-v1','attribute':'data-cfemail','value':data,
         'tag':'span','line':2,'column':0},
    ]
    assert page['linkCount'] == 0


def test_decoder_is_strict_bounded_and_rejects_non_email_or_unsafe_href():
    decoder = getattr(website_context, 'decode_cloudflare_email', None)
    assert callable(decoder)
    hex_value = _encoded('hello@example.test')
    assert decoder('/cdn-cgi/l/email-protection#' + hex_value, 'href') == 'hello@example.test'
    assert decoder('https://publisher.example.test/cdn-cgi/l/email-protection#' + hex_value,
                   'href') == 'hello@example.test'
    assert decoder(hex_value, 'data-cfemail') == 'hello@example.test'

    rejected = [
        ('/cdn-cgi/l/email-protection', 'href'),
        ('/cdn-cgi/l/email-protection?x=1#' + hex_value, 'href'),
        ('/cdn-cgi/l/email-protection?#' + hex_value, 'href'),
        ('/cdn-cgi/l/email-protection#' + hex_value + '?x=1', 'href'),
        ('//evil.example.test/cdn-cgi/l/email-protection#' + hex_value, 'href'),
        ('ftp://publisher.example.test/cdn-cgi/l/email-protection#' + hex_value, 'href'),
        ('https://user:pass@publisher.example.test/cdn-cgi/l/email-protection#' + hex_value, 'href'),
        ('https://[invalid]/cdn-cgi/l/email-protection#' + hex_value, 'href'),
        ('/cdn-cgi/l/email-protection#abc', 'href'),
        ('/cdn-cgi/l/email-protection#zzzz', 'href'),
        (_encoded('not an email'), 'data-cfemail'),
        (_encoded('one @example.test'), 'data-cfemail'),
        (_encoded('a@example.test')[:-1], 'data-cfemail'),
        ('z' * 2050, 'data-cfemail'),
        (hex_value, 'other'),
    ]
    for value, attribute in rejected:
        assert decoder(value, attribute) is None, (attribute, value[:80])
    invalid_utf8 = (bytes([1, 0xFF])).hex()
    assert decoder(invalid_utf8, 'data-cfemail') is None


def test_malformed_and_hidden_cloudflare_markup_never_becomes_a_link_or_clue():
    valid = _encoded('hidden@example.test')
    html = (f'<a href="/cdn-cgi/l/email-protection#bad">Bad</a>'
            f'<a href="/cdn-cgi/l/email-protection?x=1#{valid}">Query</a>'
            f'<span class="__cf_email__" data-cfemail="{valid}" hidden>Hidden</span>'
            f'<span class="__cf_email__" data-cfemail="{valid}" aria-hidden="true">Hidden</span>'
            f'<span class="__cf_email__" data-cfemail="{valid}" style="display: none">Hidden</span>'
            f'<span class="__cf_email__" data-cfemail="{valid}" style="visibility : hidden !important">Hidden</span>'
            f'<script><a href="/cdn-cgi/l/email-protection#{valid}">Script</a></script>'
            f'<template><a href="/cdn-cgi/l/email-protection#{valid}">Template</a></template>'
            f'<span data-cfemail="{valid}">No marker</span>'
            '<a href="/ordinary">Ordinary link</a>')
    page = website_context.extract_website_context(html, 'https://publisher.example.test/')
    assert page['emailClues'] == []
    assert [item['url'] for item in page['links']] == ['https://publisher.example.test/ordinary']


def test_cache_page_description_unconditionally_stamps_v3_for_new_parser_output():
    row = {'account_id':'123','source_url':'https://publisher.example.test/',
           'resolved_url':'https://publisher.example.test/','title':'Test page',
           'fetched_at':'2026-10-27T00:00:00Z','error':None,
           'html_gz':gzip.compress(b'<p>Example</p>')}
    page = describe_cached_page(row, {})
    assert page['status'] == 'available'
    assert page['evidenceRef']['parserVersion'] == 'website-context-v3'
    uncached = describe_cached_page({**row, 'html_gz':None}, {})
    assert uncached['status'] == 'not_cached'
    assert uncached['evidenceRef']['parserVersion'] == 'website-context-v3'


def test_known_encoded_literal_survives_after_general_link_cap():
    # Fixed bytes, not a same-helper encoder/decoder round-trip assertion.
    encoded = '4a3e2f2b270a2f322b273a262f643e2f393e'
    html = ''.join(f'<a href="/note/{i}">Note {i}</a>' for i in range(240))
    html += f'<a href="/cdn-cgi/l/email-protection#{encoded}">Team forwarding</a>'
    page = website_context.extract_website_context(html, 'https://example.test/')
    assert page['linksTruncated'] and page['linkCount'] == 240
    assert page['emailClueCount'] == 1
    assert page['emailClues'][0]['address'] == 'team@example.test'
    assert page['emailClues'][0]['kind'] == 'cloudflare_decoded'
