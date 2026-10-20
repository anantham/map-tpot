"""Pure cached-page evidence extraction. No contact/ownership classification."""
from html.parser import HTMLParser
import re
from urllib.parse import unquote, urljoin, urlsplit

from src.enrichment.public_page_claims import extract_public_page_claims

EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
SKIP = {'script','style','noscript','svg','template','head'}
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}


def _http(href, base):
    try:
        value = urljoin(base, href.strip())
        parts = urlsplit(value)
        if (parts.scheme in ('https','http') and parts.hostname and not parts.username
                and not parts.password and not any(ord(c)<32 for c in value)):
            return value
    except (ValueError, TypeError):
        pass
    return None


def _context(text, start, end):
    return text[max(0,start-120):min(len(text),max(start+1,end)+180)].strip()[:500]


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.anchors, self.forms, self.stack = [], [], [], []
        self.position, self.hidden = 0, 0
        self.anchor = self.form = None
        self.base_href = None

    def _emit(self, text):
        if self.hidden:
            return
        text = ' '.join(text.split())
        if text:
            self.parts.append(text+' ')
            self.position += len(text)+1
            if self.anchor is not None:
                self.anchor['labelParts'].append(text)

    def _anchor_end(self):
        if self.anchor is not None:
            self.anchor['end'] = self.position
            self.anchors.append(self.anchor)
            self.anchor = None

    def _form_end(self):
        if self.form is not None:
            self.form['end'] = self.position
            self.forms.append(self.form)
            self.form = None

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag=='base' and self.base_href is None and not any(
                hidden and ancestor!='head' for ancestor,hidden in self.stack):
            self.base_href = attrs.get('href') or ''
        hidden = tag in SKIP or 'hidden' in attrs or str(attrs.get('aria-hidden','')).lower()=='true'
        if tag not in VOID:
            self.stack.append((tag,hidden))
            self.hidden += int(hidden)
        if self.hidden or hidden:
            return
        if tag=='a':
            self._anchor_end()
            self.anchor = {'href':attrs.get('href') or '', 'start':self.position,
                'labelParts':[], 'fallback':attrs.get('aria-label') or attrs.get('title') or ''}
        elif tag=='img':
            self._emit(attrs.get('alt') or '')
        elif tag=='form':
            self._form_end()
            self.form = {'action':attrs.get('action') or '', 'start':self.position,
                         'messageField':False, 'method':attrs.get('method') or 'get'}
        elif tag=='textarea' and self.form is not None:
            self.form['messageField'] = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if not self.hidden:
            if tag=='a': self._anchor_end()
            elif tag=='form': self._form_end()
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                if any(hidden for _,hidden in self.stack[i+1:]):
                    return  # A different ancestor's end tag cannot close a hidden block.
                self.hidden -= sum(int(hidden) for _,hidden in self.stack[i:])
                del self.stack[i:]
                break

    def handle_data(self, data):
        self._emit(data)


def extract_website_context(html, base_url):
    """Extract all literal affordances before bounded presentation; no inference."""
    parser = _Page()
    parser.feed(html)
    parser.close()
    parser._anchor_end()
    parser._form_end()
    text = ''.join(parser.parts).strip()
    declared_base = _http(parser.base_href,base_url) if parser.base_href is not None else None
    if parser.base_href is not None:
        base_url = declared_base or ''
    links, emails, seen_links, seen_emails = [], [], set(), set()

    def email(address, kind, label, start, end):
        context = _context(text,start,end)
        key = (address,kind,context)
        if EMAIL.fullmatch(address) and key not in seen_emails:
            seen_emails.add(key)
            emails.append({'address':address,'kind':kind,'label':label,'context':context})

    for anchor in parser.anchors:
        href = anchor['href'].strip()
        label = (' '.join(anchor['labelParts']) or anchor['fallback']).strip()[:300]
        if href.lower().startswith('mailto:'):
            for address in re.split('[,;]',unquote(href[7:].split('?',1)[0])):
                email(address.strip(),'mailto',label,anchor['start'],anchor['end'])
        elif href and not href.startswith('#') and (url := _http(href,base_url)):
            key = (url,label)
            if key not in seen_links:
                seen_links.add(key)
                links.append({'url':url,'label':label or url,
                              'context':_context(text,anchor['start'],anchor['end'])})
    for match in EMAIL.finditer(text):
        email(match.group(),'visible_text','Visible email text',match.start(),match.end())
    forms = [{'action':_http(form['action'],base_url),'method':form['method'],
              'context':_context(text,form['start'],form['end']),'tested':False}
             for form in parser.forms if form['messageField']]
    return {'text':text[:6000],'textTruncated':len(text)>6000,
        'publicClaims':extract_public_page_claims(html,base_url),
        'linkBaseFromMarkup':bool(declared_base),'unclosedHiddenMarkup':bool(parser.hidden),
        'links':links[:200],'linkCount':len(links),'linksTruncated':len(links)>200,
        'emailClues':emails[:100],'emailClueCount':len(emails),'emailCluesTruncated':len(emails)>100,
        'messageForms':forms[:20],'formCount':len(forms),'formsTruncated':len(forms)>20,
        'boundary':'Literal page text/links, not verified ownership, authorship or reviewed contact routes. '
                   'Emails can belong to organisations or third parties; forms were not tested or submitted. '
                   'Scripts/templates/hidden attributes are omitted; CSS and JavaScript are not evaluated.'}
