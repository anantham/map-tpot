"""Pure cached-page evidence extraction. No contact/ownership classification."""
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import unquote, urljoin, urlsplit

from src.enrichment.public_page_claims import extract_public_page_claims

EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
SKIP = {'script','style','noscript','svg','template','head'}
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
EMAIL_PROTECTION_PATH = '/cdn-cgi/l/email-protection'
HEX = re.compile(r'[0-9a-fA-F]+\Z')


def decode_cloudflare_email(value, attribute):
    """Decode one bounded Cloudflare XOR clue, returning only a single email string."""
    if not isinstance(value,str) or attribute not in ('href','data-cfemail'):
        return None
    if value != value.strip() or any(ord(char)<32 or ord(char)==127 for char in value):
        return None
    if attribute=='href':
        try:
            parts=urlsplit(value)
            has_query='?' in value.split('#',1)[0]
            hostname=parts.hostname
        except (TypeError,ValueError):
            return None
        if (parts.path!=EMAIL_PROTECTION_PATH or parts.query or has_query
                or (parts.scheme and parts.scheme.lower() not in ('http','https'))):
            return None
        if parts.scheme or parts.netloc:
            if (parts.scheme.lower() not in ('http','https') or not hostname
                    or parts.username is not None or parts.password is not None):
                return None
        elif not value.startswith('/') or value.startswith('//'):
            return None
        encoded=parts.fragment
    else:
        encoded=value
    if (len(encoded)<4 or len(encoded)>2048 or len(encoded)%2
            or HEX.fullmatch(encoded) is None):
        return None
    try:
        raw=bytes.fromhex(encoded)
        key=raw[0]
        address=bytes(byte^key for byte in raw[1:]).decode('utf-8')
    except (ValueError,UnicodeDecodeError):
        return None
    if (any(char.isspace() or unicodedata.category(char) in ('Cc','Cf') for char in address)
            or EMAIL.fullmatch(address) is None):
        return None
    return address


def _is_email_protection_endpoint(href):
    try:
        return urlsplit(href).path==EMAIL_PROTECTION_PATH
    except (TypeError,ValueError):
        return False


def _hidden_style(attrs):
    style=(attrs.get('style') or '').lower()
    return bool(re.search(r'(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)(?:\s*!important)?\s*(?:;|$)',style))


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
        self.cloudflare = []
        self.activeCloudflare = []
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
            for clue in self.activeCloudflare:
                clue['labelParts'].append(text)

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
        attrs = {key:(value or '') for key,value in attributes}
        if tag=='base' and self.base_href is None and not any(
                hidden and ancestor!='head' for ancestor,hidden,_ in self.stack):
            self.base_href = attrs.get('href') or ''
        hidden = (tag in SKIP or 'hidden' in attrs
            or attrs.get('aria-hidden','').lower()=='true' or _hidden_style(attrs))
        line,column=self.getpos()
        clue=None
        if (not self.hidden and not hidden and attrs.get('data-cfemail')
                and '__cf_email__' in (attrs.get('class') or '').split()):
            value=attrs['data-cfemail']
            address=decode_cloudflare_email(value,'data-cfemail')
            if address is not None:
                clue={'address':address,'start':self.position,'end':self.position,
                    'labelParts':[],'fallback':attrs.get('aria-label') or attrs.get('title') or '',
                    'decoding':{'method':'cloudflare-xor-v1','attribute':'data-cfemail',
                        'value':value,'tag':tag,'line':line,'column':column}}
        if tag not in VOID:
            self.stack.append((tag,hidden,clue))
            self.hidden += int(hidden)
            if clue is not None:
                self.activeCloudflare.append(clue)
        elif clue is not None:
            clue['label']=' '.join(clue['labelParts']) or clue['fallback'] or 'Cloudflare-protected address'
            self.cloudflare.append(clue)
        if self.hidden or hidden:
            return
        if tag=='a':
            self._anchor_end()
            self.anchor = {'href':attrs.get('href') or '', 'start':self.position,
                'labelParts':[], 'fallback':attrs.get('aria-label') or attrs.get('title') or '',
                'tag':tag,'line':line,'column':column}
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
                if any(hidden for _,hidden,_ in self.stack[i+1:]):
                    return  # A different ancestor's end tag cannot close a hidden block.
                closed=self.stack[i:]
                self.hidden -= sum(int(hidden) for _,hidden,_ in closed)
                del self.stack[i:]
                for _,_,clue in reversed(closed):
                    if clue is not None:
                        if clue in self.activeCloudflare:
                            self.activeCloudflare.remove(clue)
                        clue['end']=self.position
                        clue['label']=' '.join(clue['labelParts']) or clue['fallback'] or 'Cloudflare-protected address'
                        self.cloudflare.append(clue)
                break

    def handle_data(self, data):
        self._emit(data)


def extract_website_context(html, base_url):
    """Extract saved affordances and labelled decoded markup; no ownership inference."""
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

    def email(address, kind, label, start, end, decoding=None):
        context = _context(text,start,end)
        key = (address,kind,context,tuple(decoding.items()) if decoding else None)
        if EMAIL.fullmatch(address) and key not in seen_emails:
            seen_emails.add(key)
            item={'address':address,'kind':kind,'label':label,'context':context}
            if decoding is not None:
                item['decoding']=decoding
            emails.append(item)

    for anchor in parser.anchors:
        href = anchor['href']
        label = (' '.join(anchor['labelParts']) or anchor['fallback']).strip()[:300]
        if _is_email_protection_endpoint(href):
            address=decode_cloudflare_email(href,'href')
            if address is not None:
                email(address,'cloudflare_decoded',label or 'Cloudflare-protected address',
                    anchor['start'],anchor['end'],{'method':'cloudflare-xor-v1','attribute':'href',
                    'value':href,'tag':anchor['tag'],'line':anchor['line'],'column':anchor['column']})
            continue
        href=href.strip()
        if href.lower().startswith('mailto:'):
            for address in re.split('[,;]',unquote(href[7:].split('?',1)[0])):
                email(address.strip(),'mailto',label,anchor['start'],anchor['end'])
        elif href and not href.startswith('#') and (url := _http(href,base_url)):
            key = (url,label)
            if key not in seen_links:
                seen_links.add(key)
                links.append({'url':url,'label':label or url,
                              'context':_context(text,anchor['start'],anchor['end'])})
    for clue in parser.cloudflare:
        email(clue['address'],'cloudflare_decoded',clue['label'][:300],clue['start'],clue['end'],clue['decoding'])
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
        'boundary':'Saved page text/links and method-labelled decoded email markup, not verified ownership, authorship or reviewed contact routes. '
                   'Emails can belong to organisations or third parties; forms were not tested or submitted. '
                   'Scripts/templates/explicitly hidden markup are omitted; external CSS and JavaScript are not evaluated.'}
