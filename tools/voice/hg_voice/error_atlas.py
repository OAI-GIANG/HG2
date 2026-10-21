"""Deterministic Vietnamese text-error diagnostics; never infers acoustic causes."""
import unicodedata
from collections import Counter
from .metrics import normalize_text, edit_distance


def _without_marks(text: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFD', text)
                   if unicodedata.category(ch) != 'Mn')


def _without_punctuation(text: str) -> str:
    return ''.join(ch for ch in text if not unicodedata.category(ch).startswith('P'))


def classify_difference(reference: str, hypothesis: str) -> str:
    """Return one observable text-difference class, not an acoustic root cause."""
    if not isinstance(reference, str) or not isinstance(hypothesis, str):
        raise TypeError('reference and hypothesis must be strings')
    if reference == hypothesis:
        return 'exact_match'
    ref, hyp = normalize_text(reference), normalize_text(hypothesis)
    if ref == hyp:
        return 'whitespace_or_unicode_normalization'
    if _without_marks(ref) == _without_marks(hyp):
        return 'diacritic_difference'
    if _without_punctuation(ref) == _without_punctuation(hyp):
        return 'punctuation_only_difference'
    if ref.replace(' ', '') == hyp.replace(' ', ''):
        return 'whitespace_or_tokenization_difference'
    if not ref and hyp:
        return 'insertion_or_empty_reference'
    if ref and not hyp:
        return 'deletion_or_empty_hypothesis'
    ref_words, hyp_words = ref.split(), hyp.split()
    if len(ref_words) == len(hyp_words) and edit_distance(ref_words, hyp_words) > 0:
        return 'lexical_or_word_sequence_difference'
    return 'mixed_or_other_difference'


def build_error_atlas(pairs, *, include_examples=False, max_examples_per_class=3):
    """Aggregate classes with explicit denominators; examples are opt-in.

    `pairs` is an iterable of mappings with string `reference` and `hypothesis`.
    Do not enable examples for corpora whose license/privacy policy forbids excerpts.
    """
    if max_examples_per_class < 0:
        raise ValueError('max_examples_per_class must be non-negative')
    buckets = {}
    total = 0
    for index, pair in enumerate(pairs, 1):
        if not isinstance(pair, dict) or not isinstance(pair.get('reference'), str) or not isinstance(pair.get('hypothesis'), str):
            raise ValueError(f'pair {index}: expected string reference and hypothesis')
        total += 1
        category = classify_difference(pair['reference'], pair['hypothesis'])
        bucket = buckets.setdefault(category, {'count': 0, 'examples': []})
        bucket['count'] += 1
        if include_examples and len(bucket['examples']) < max_examples_per_class:
            bucket['examples'].append({'reference': pair['reference'], 'hypothesis': pair['hypothesis']})
    return {
        'schema_version': '1',
        'diagnostic_scope': 'observable_text_difference_not_acoustic_causality',
        'utterance_denominator': total,
        'classes': {name: {'count': data['count'], 'denominator': total,
                           'rate': data['count'] / total if total else None,
                           **({'examples': data['examples']} if include_examples else {})}
                    for name, data in sorted(buckets.items())},
        'status': 'DIAGNOSTIC_ONLY_NOT_ACCEPTANCE',
        'examples_included': bool(include_examples),
    }
