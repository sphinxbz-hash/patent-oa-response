"""Conservative evidence metadata derived from extracted text and docket records.

Inferences remain auditable candidates, never a grant/acceptance determination,
target pending-claim designation, or replacement for explicit user metadata.
"""
import re

ENGLISH = set('the of and to in for with is are be a an that this which as by from on or not '
              'claim claims wherein according said comprising configured method device controller '
              'current input output application amended inventive step'.split())
FOREIGN = set('der die das den dem des und ein eine einer ist werden zur zum mit nach dadurch '
              'gekennzeichnet revendication revendications selon dans les des une et pour le la du '
              'dispositif presente pedido reivindicacoes para uma dos das pelo pela '
              'el los las una por del con segun'.split())


def _user_set(document, field):
    return any(field in entry.get('before', {}) for entry in document.get('metadata_history', []))


def _infer(document, field, value, evidence):
    if _user_set(document, field) or document.get(field) == value:
        return 0
    document[field] = value
    document.setdefault('metadata_inference', {})[field] = dict(evidence, value=value)
    return 1


def english_evidence(text):
    """Identify substantial English body text; titles/country are not evidence.

    Abstain on short, mixed-script or unsupported languages. This intentionally
    does not attempt general language detection or measure OCR accuracy.
    """
    letters = [c for c in str(text) if c.isalpha()]
    latin_share = sum(c.isascii() for c in letters) / max(len(letters), 1)
    words = re.findall(r'\b[a-z]+\b', str(text).lower())
    hits = sum(w in ENGLISH for w in words)
    foreign_hits = sum(w in FOREIGN for w in words)
    distinct = len(set(words) & ENGLISH)
    if len(words) < 80 or latin_share < .8 or distinct < 8 or hits / len(words) < .16 or hits <= foreign_hits * 2:
        return None
    return dict(method='body_vocabulary_v1', token_count=len(words), english_hits=hits,
                distinct_english_hits=distinct, english_share=round(hits / len(words), 4),
                latin_share=round(latin_share, 4), status='inferred_not_verified')


def _ep_key(value):
    match = re.fullmatch(r'EP\s*(\d{8})(?:\.\d)?(?:A)?', str(value or '').strip().upper())
    return match.group(1) if match else None


def enrich_case_documents(case):
    """Repair fresh and already cached imports alike; return changed-field count."""
    documents = case.get('documents') or []
    changes = 0
    for doc in documents:
        if str(doc.get('language') or '').lower() in ('', 'unknown', 'und') and not _user_set(doc, 'language'):
            text = doc.get('text') or '\n'.join(str(p.get('text') or '') for p in doc.get('pages', []))
            evidence = english_evidence(text)
            if evidence:
                changes += _infer(doc, 'language', 'en', evidence)
        # Earlier ZIP code hints incorrectly made maintenance forms substantive.
        if doc.get('country') == 'EP' and doc.get('role') in ('oa', 'response') and re.match(
                r'^(?:invitation to declare )?maintenance of (?:the )?application\b',
                str(doc.get('title') or '').strip(), re.I):
            changes += _infer(doc, 'role', 'other', dict(method='ep_administrative_title',
                                                      source_title=doc['title']))

    by_id = {doc.get('id'): doc for doc in documents}
    seen = set()
    for cycle in reversed(case.get('cycles') or []):
        reply = by_id.get(cycle.get('response_id'))
        app = _ep_key(cycle.get('application'))
        if not app or not reply or (app, reply['id']) in seen:
            continue
        seen.add((app, reply['id']))
        if (reply.get('role') != 'response' or reply.get('country') != 'EP' or
                _ep_key(reply.get('application')) != app or not reply.get('date') or
                reply.get('version_status') in ('auxiliary', 'not_entered') or
                reply.get('cycle_id') not in (None, '', reply['id'])):
            continue
        evidence = dict(method='same_application_and_filing_date', response_id=reply['id'],
                        application=cycle['application'], filing_date=reply['date'],
                        source_url=cycle.get('source_url', ''),
                        status='date_based_candidate_not_acceptance')
        changes += _infer(reply, 'cycle_id', reply['id'], evidence)
        for doc in documents:
            if doc.get('country') != 'EP' or _ep_key(doc.get('application')) != app:
                continue
            if doc.get('role') != 'claims' or doc.get('date') != reply['date']:
                continue
            if not doc.get('cycle_id'):
                changes += _infer(doc, 'cycle_id', reply['id'], evidence)
            if (doc.get('cycle_id') == reply['id'] and not doc.get('requires_clean_text') and
                    doc.get('version_status') in (None, '', 'unknown')):
                changes += _infer(doc, 'version_status', 'reference', evidence)
        oa = by_id.get(cycle.get('response_oa_id'))
        if (oa and oa.get('country') == 'EP' and _ep_key(oa.get('application')) == app and
                oa.get('role') == 'oa' and oa.get('date') and oa['date'] <= reply['date'] and not oa.get('cycle_id')):
            changes += _infer(oa, 'cycle_id', reply['id'], dict(evidence, method='same_application_preceding_oa'))
    if changes:
        case['exports_stale'] = bool(case.get('exports'))
    return changes
