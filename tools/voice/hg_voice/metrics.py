"""Deterministic WER/CER helpers for approved, consented benchmark transcripts."""
import unicodedata


def normalize_text(text: str) -> str:
    """NFC, casefold, trim/collapse whitespace; punctuation is intentionally retained."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def edit_distance(reference, hypothesis):
    """Levenshtein distance over a sequence of tokens/code points, O(min(n,m)) memory."""
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for i, ref_item in enumerate(reference, 1):
        current = [i]
        for j, hyp_item in enumerate(hypothesis, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (ref_item != hyp_item),
            ))
        previous = current
    return previous[-1]


def score_pair(reference: str, hypothesis: str) -> dict:
    """Return normalized reference units, edit counts and rates; empty reference is undefined."""
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    ref_words, hyp_words = ref.split(), hyp.split()
    ref_chars, hyp_chars = list(ref), list(hyp)
    word_errors = edit_distance(ref_words, hyp_words)
    char_errors = edit_distance(ref_chars, hyp_chars)
    return {
        "reference_words": len(ref_words),
        "word_errors": word_errors,
        "wer": (word_errors / len(ref_words)) if ref_words else None,
        "reference_characters": len(ref_chars),
        "character_errors": char_errors,
        "cer": (char_errors / len(ref_chars)) if ref_chars else None,
    }
