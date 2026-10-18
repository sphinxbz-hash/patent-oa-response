"""Deterministic evidence selection and limited Office Action classification.

This module locates evidence. It does not determine patentability, legal support,
foreign office acceptance, or a verified filing deadline.
"""

import re
from datetime import date, timedelta


BR_PRELIM_SOURCE = ('https://www.gov.br/inpi/pt-br/servicos/patentes/novos-guias-rapidos/'
                    'guia-rapido-sobre-exigencia-tecnica-preliminar/')
ISSUE_RULES = (
    ('inventive_step', 'Inventive step', r'inventive\s+step|non[- ]?obvious|obviousness|atividade\s+inventiva|art(?:icle|igo)?\.?\s*56\b|35\s*U\.?S\.?C\.?\s*(?:§\s*)?103\b'),
    ('novelty', 'Novelty', r'\bnovelty\b|\bnovidade\b|anticipat(?:ed|ion)|art(?:icle|igo)?\.?\s*54\b|35\s*U\.?S\.?C\.?\s*(?:§\s*)?102\b'),
    ('clarity', 'Clarity', r'\bclarity\b|\bclareza\b|\bindefinite|art(?:icle|igo)?\.?\s*84\b'),
    ('support', 'Disclosure and support', r'written\s+description|added\s+matter|sufficiency|enablement|insufici[eê]ncia|suporte|123\s*\(2\)|112\s*\(a\)'),
    ('unity', 'Unity of invention', r'unity\s+of\s+invention|unidade\s+de\s+inven|restriction\s+requirement'),
    ('eligibility', 'Subject matter eligibility', r'patent[- ]eligible|eligibility|mat[eé]ria\s+patente[aá]vel|35\s*U\.?S\.?C\.?\s*(?:§\s*)?101\b'),
    ('formalities', 'Formal requirements', r'formal\s+(?:requirement|objection)|formalidade|exig[eê]ncia\s+formal'),
)
PATENT_CITATION = re.compile(r'\b(?:US|EP|WO|CN|JP|KR|BR|GB|DE|FR)\s*\d[\d\s/.,-]{4,24}\s*[ABCUTY]\d?\b', re.I)


def document_text(document):
    if not document:
        return ''
    return str(document.get('draft_text') or document.get('text') or '\n'.join(str(p.get('text') or '') for p in document.get('pages', []))).strip()


def _english(document):
    return str(document.get('language') or '').strip().lower() in ('en', 'eng', 'english', 'en-us', 'en-gb')


def _available(document):
    return (document.get('status') in ('downloaded', 'imported') and bool(document_text(document))
            and not document.get('requires_clean_text'))


def _latest(documents):
    return max(documents, key=lambda d: (str(d.get('date') or ''), str(d.get('id') or '')), default=None)


def _number(value):
    raw = str(value or '').upper().strip()
    ep_application = re.fullmatch(r'EP\s*(\d{8})\.\d(?:A)?', raw)
    if ep_application:
        return 'EP' + ep_application.group(1)
    value = re.sub(r'[^A-Z0-9]', '', str(value or '').upper())
    return re.sub(r'[ABCUTY]\d?$', '', value)


def _member_keys(document, family):
    keys = {_number(document.get(k)) for k in ('application', 'publication') if document.get(k)}
    for row in family:
        row_keys = {_number(row.get(k)) for k in ('application', 'publication') if row.get(k)}
        if keys.intersection(row_keys):
            keys.update(row_keys)
    return keys


def _same_member(first, second, family):
    if first.get('country') != second.get('country'):
        return False
    first_keys, second_keys = _member_keys(first, family), _member_keys(second, family)
    return not (first_keys and second_keys) or bool(first_keys.intersection(second_keys))


def _in_source_member(document, member, family):
    member = str(member or 'EP').upper().strip()
    if len(member) == 2:
        return str(document.get('country') or '').upper() == member
    return _number(member) in _member_keys(document, family)


def _cycle_matches(claims, response):
    if not response:
        return False
    return bool(claims.get('response_id') == response.get('id') or
                (claims.get('cycle_id') and claims.get('cycle_id') == response.get('cycle_id')))


def _deadline(settings, target_country):
    supplied = settings.get('deadline') or {}
    result = dict(status='unverified', verified=False, due_date=None, nominal_date=None,
                  rule_id=supplied.get('rule_id') or '', trigger_date=supplied.get('trigger_date') or '',
                  source_url=supplied.get('source_url') or '',
                  explanation='No verified deadline. Select an applicable rule and verify the official trigger.',
                  fee=dict(status='unverified', amount=None, currency=None,
                           explanation='Applicable fee and entity status have not been verified.'))
    if target_country == 'BR' and supplied.get('rule_id') == 'BR_PRELIM_90' and supplied.get('source_url'):
        try:
            trigger = date.fromisoformat(str(supplied.get('trigger_date') or ''))
        except ValueError:
            result['explanation'] = 'The preliminary requirement trigger must be a valid ISO publication date.'
        else:
            result.update(nominal_date=(trigger + timedelta(days=90)).isoformat(), rule_source_url=BR_PRELIM_SOURCE,
                          explanation='Nominal 90 calendar days after the supplied RPI publication date for a '
                          'Brazilian preliminary technical requirement. Trigger applicability and holiday '
                          'adjustment remain unverified. This is not a verified filing deadline.')
    return result


def _oa_issues(oa):
    if not oa:
        return []
    pages = oa.get('pages') or [{'number': None, 'text': document_text(oa)}]
    issues = []
    for page in pages:
        text = str(page.get('text') or '')
        citations = list(dict.fromkeys(re.sub(r'\s+', '', m.group()).upper() for m in PATENT_CITATION.finditer(text)))
        for category, title, pattern in ISSUE_RULES:
            matched = [line.strip() for line in text.splitlines() if re.search(pattern, line, re.I)]
            if matched:
                issues.append(dict(category=category, title=title, excerpt='\n'.join(matched),
                                   page=page.get('number'), source_id=oa.get('id'), citations=citations,
                                   method='keyword_rule', status='requires_context_review'))
        if citations and not any(i['source_id'] == oa.get('id') and i['page'] == page.get('number') for i in issues):
            issues.append(dict(category='citation', title='Cited patent document', excerpt=text,
                               page=page.get('number'), source_id=oa.get('id'), citations=citations,
                               method='patent_number_pattern', status='requires_context_review'))
    return issues


def _support_rows(settings, original):
    result = []
    for supplied in settings.get('support_rows') or []:
        row = {key: supplied.get(key, '') for key in ('claim', 'change', 'basis', 'source_id', 'page')}
        row.update(status='unverified', legal_support='unverified',
                   note='A citation to the target application as originally filed is required.')
        if original and row['source_id'] == original.get('id'):
            pages = original.get('pages') or []
            page = next((p for p in pages if str(p.get('number')) == str(row['page'])), None)
            basis = re.sub(r'\s+', ' ', str(row['basis'])).strip()
            source = re.sub(r'\s+', ' ', str(page.get('text') or '')) if page else ''
            if basis and basis in source:
                row.update(status='source_located',
                           note='Quoted text located on the specified target original page. Legal support is unverified.')
            else:
                row['note'] = 'Target original selected, but this basis text was not located on the specified page.'
        result.append(row)
    return result


def _adapt_response(case, response, family):
    """Replace only known family identities, never statutes or technical wording."""
    override = str((case.get('settings') or {}).get('response_override') or '').strip()
    text = override or document_text(response)
    result = dict(text=text, log=[], foreign_legal_references=[], origin='user_authored' if override else 'family_response')
    target_application = str(case.get('target_application') or '').strip()
    if response and not override and target_application:
        identities = {str(response.get(key)) for key in ('application', 'publication') if response.get(key)}
        source_keys = _member_keys(response, family)
        for row in family:
            row_keys = {_number(row.get(key)) for key in ('application', 'publication') if row.get(key)}
            if source_keys.intersection(row_keys):
                identities.update(str(row[key]) for key in ('application', 'publication') if row.get(key))
        identities.discard(target_application)
        if identities:
            pattern = re.compile(r'(?<![A-Za-z0-9])(?:' + '|'.join(re.escape(x) for x in sorted(identities, key=len, reverse=True))
                                 + r')(?![A-Za-z0-9]|[./-]\d)')
            counts = {}

            def replace(match):
                identity = match.group()
                counts[identity] = counts.get(identity, 0) + 1
                return target_application

            result['text'] = pattern.sub(replace, text)
            result['log'] = [dict(action='replace_known_application_identity', source_id=response.get('id'),
                                  old=identity, new=target_application, occurrences=count,
                                  explanation='Exact known family identifier replaced; technical argument text preserved.')
                             for identity, count in counts.items()]
    target = str(case.get('target_country') or 'BR').upper()
    legal_patterns = [('EP', r'\bEPC\b|\bEPO\b|European Patent (?:Convention|Office)'),
                      ('US', r'\b35\s*U\.?\s*S\.?\s*C\.?|\b37\s*C\.?\s*F\.?\s*R\.?|\bUSPTO\b'),
                      ('WO', r'\bPCT\b|international preliminary examination')]
    for country, pattern in legal_patterns:
        if country != target:
            result['foreign_legal_references'].extend(m.group() for m in re.finditer(pattern, result['text'], re.I))
    result['foreign_legal_references'] = list(dict.fromkeys(result['foreign_legal_references']))
    return result


def _terms(text):
    stopwords = {'claim', 'claims', 'wherein', 'comprising', 'thereof', 'therein', 'which', 'with', 'from', 'that',
                 'this', 'said', 'having', 'invention', 'inventive', 'novelty', 'step', 'article', 'document',
                 'cited', 'applicant', 'application', 'response', 'does', 'over', 'under', 'patent', 'disputed'}
    return set(re.findall(r'\b[a-z]{4,}\b', str(text).lower())) - stopwords


def _strategy_rows(issues, response, claims, pending):
    reply_text = document_text(response)
    reply_citations = {re.sub(r'\s+', '', match.group()).upper() for match in PATENT_CITATION.finditer(reply_text)}
    reply_terms = _terms(reply_text)
    amendment_terms = _terms(document_text(claims)) - _terms(document_text(pending)) if claims and pending else set()
    rows = []
    for issue in issues:
        citations = sorted(set(issue['citations']).intersection(reply_citations))
        shared = sorted(_terms(issue['excerpt']).intersection(reply_terms))
        amendments = sorted(_terms(issue['excerpt']).intersection(amendment_terms))
        if response and (citations or len(shared) >= 2):
            status, action = 'reuse_argument', 'Reuse the selected family argument as a candidate response to this objection.'
            evidence = {'shared_citations': citations, 'shared_terms': shared, 'response_id': response.get('id')}
        elif amendments:
            status, action = 'reuse_amendment', 'Reuse the selected claim wording as a candidate amendment for this objection.'
            evidence = {'changed_terms_in_objection': amendments, 'claims_id': claims.get('id')}
        else:
            status, action = 'separate_response', 'Supply a separate source backed or user authored response for this objection.'
            evidence = {'reason': 'No supported literal citation or wording match was found.'}
        rows.append(dict(issue=issue['title'], source_id=issue['source_id'], page=issue['page'],
                         action=action, status=status, method='rule_based_candidate', evidence=evidence,
                         limitation='Literal matching proposes a reuse candidate; it does not determine legal applicability or success.'))
    return rows


def analyze_case(case):
    """Return analysis without modifying the case or substituting explicit IDs."""
    settings = case.get('settings') or {}
    documents = case.get('documents') or []
    family = case.get('family') or []
    target = str(case.get('target_country') or 'BR').upper()
    member = settings.get('source_member') or 'EP'
    # Material availability changes after manual imports. Recompute it below.
    gaps = []
    if not family and any('尚未核验同族' in str(gap) for gap in case.get('research_gaps') or []):
        gaps.append('Family discovery remains unverified; a failed lookup does not establish absence of family members.')

    def select(key, predicate, label, candidates=None):
        selected_id = settings.get(key)
        pool = documents if candidates is None else candidates
        if selected_id:
            document = next((d for d in documents if d.get('id') == selected_id), None)
            if document is None:
                gaps.append(f'Selected {label} {selected_id} is missing; no substitute was selected.')
                return None
            if not predicate(document) or not _available(document):
                gaps.append(f'Selected {label} {selected_id} has an incompatible role, member, version, language, status, or no extracted text.')
                return None
            return document
        return _latest([d for d in pool if predicate(d) and _available(d)])

    def foreign_response(d):
        return (d.get('role') == 'response' and _in_source_member(d, member, family) and _english(d)
                and d.get('version_status') not in ('not_entered', 'auxiliary'))

    def foreign_claims(d):
        return (d.get('role') == 'claims' and _in_source_member(d, member, family) and _english(d)
                and d.get('version_status') in ('granted', 'reference', 'pending'))

    response = select('selected_response_id', foreign_response, 'response')
    explicit_claims = bool(settings.get('selected_claims_id'))
    if explicit_claims:
        claims = select('selected_claims_id', foreign_claims, 'claims')
    else:
        eligible = [d for d in documents if foreign_claims(d) and _available(d)]
        if settings.get('selected_response_id') and response:
            eligible = [d for d in eligible if _same_member(d, response, family)]
        grants = [d for d in eligible if d.get('version_status') == 'granted']
        # A newer response lacking its claims must not displace a complete earlier cycle.
        responses = [response] if settings.get('selected_response_id') else [d for d in documents if foreign_response(d) and _available(d)]
        pairs = [(claim, reply) for claim in eligible for reply in responses
                 if reply and _same_member(claim, reply, family) and _cycle_matches(claim, reply)]
        paired_claims = max(pairs, key=lambda pair: (str(pair[1].get('date') or ''), str(pair[0].get('date') or '')), default=(None, None))[0]
        claims = _latest(grants) or paired_claims
    if claims:
        if settings.get('selected_response_id'):
            if response and not _same_member(claims, response, family):
                gaps.append('Selected claims and response belong to different known family members; response reuse is disabled.')
                response = None
            elif (response and claims.get('version_status') != 'granted' and (claims.get('response_id') or claims.get('cycle_id'))
                  and not _cycle_matches(claims, response)):
                gaps.append('Selected claims and response belong to different response cycles; response reuse is disabled.')
                response = None
        else:
            responses = [d for d in documents if foreign_response(d) and _available(d) and _same_member(claims, d, family)]
            if claims.get('version_status') != 'granted' and (claims.get('response_id') or claims.get('cycle_id')):
                responses = [d for d in responses if _cycle_matches(claims, d)]
            response = _latest(responses)
        if response and not (_member_keys(claims, family) and _member_keys(response, family)):
            gaps.append('Source country matches, but the response and claims application member pairing is unverified.')

    target_keys = _member_keys({'application': case.get('target_application')}, family)

    def target_member(d):
        keys = _member_keys(d, family)
        return (str(d.get('country') or '').upper() == target
                and (not keys or not target_keys or bool(keys.intersection(target_keys))))

    def is_pending(d):
        return d.get('role') == 'claims' and target_member(d) and d.get('version_status') == 'pending'

    pending = select('pending_claims_id', is_pending, 'target pending claims')
    oa = select('target_oa_id', lambda d: d.get('role') == 'oa' and target_member(d), 'target OA')
    original = select('original_id', lambda d: d.get('role') == 'original' and target_member(d), 'target original')
    sources = dict(response=response, claims=claims, pending=pending, oa=oa, original=original)
    labels = dict(response='English family response', claims='English grant or response cycle claims',
                  pending='target pending claims baseline', oa='target Office Action', original='target original filing')
    for key, source in sources.items():
        if source is None:
            gaps.append(f'Missing usable {labels[key]}.')
    for document in documents:
        recognition = document.get('ocr') or {}
        if recognition.get('status') in ('partial', 'failed', 'unavailable') or recognition.get('review_pages') or recognition.get('empty_pages'):
            gaps.append(f'OCR source {document.get("id", "Document")}: some pages are unreadable or require verification against the original PDF.')
        if document.get('requires_clean_text'):
            gaps.append(f'Marked source {document.get("id", "Document")}: clean text required before claims or response reuse.')
        if document.get('status') in ('downloaded', 'imported') and not document_text(document):
            gaps.append(f'{document.get("id", "Document")} has no extracted text; a scan may require OCR or manual text entry.')
    baseline_usable = bool(pending and _english(pending))
    if pending and not baseline_usable:
        gaps.append('The target pending claims are not identified as English; no cross language target redline is produced.')
    latest_pending = _latest([d for d in documents if is_pending(d) and _available(d)])
    baseline_latest = bool(pending and latest_pending and pending.get('id') == latest_pending.get('id'))
    if pending and not baseline_latest:
        gaps.append('The selected pending baseline is not the latest supplied pending version; immediate prior version is unverified.')
    issues = _oa_issues(oa)
    if oa and not issues:
        gaps.append('No supported OA heading or patent citation pattern was detected; the full OA requires review.')
    support = _support_rows(settings, original)
    if not support or any(row['status'] != 'source_located' for row in support):
        gaps.append('Amendment support in the target original remains unverified.')
    deadline = _deadline(settings, target)
    gaps.append('Filing deadline and fees remain unverified.')
    strategy = _strategy_rows(issues, response, claims, pending)
    adaptation = _adapt_response(case, response, family)
    if adaptation['foreign_legal_references']:
        gaps.append('Foreign legal or procedural references remain unresolved: ' + ', '.join(adaptation['foreign_legal_references']) +
                    '. No local law substitution was made.')
    if response and not case.get('target_application'):
        gaps.append('Target application identity is missing; foreign response identifiers have not been adapted.')
    return dict(sources=sources, issues=issues, strategy=strategy, support=support, deadline=deadline,
                adaptation=adaptation,
                gaps=list(dict.fromkeys(gaps)), baseline_usable=baseline_usable, baseline_latest=baseline_latest,
                acceptance=dict(status='not_verified', explanation='Applicant submissions are arguments, not official acceptance. '
                                'Grant metadata alone does not establish acceptance of a particular argument.'),
                review_enabled=bool(settings.get('review_enabled')), method='deterministic_rules_no_llm')
