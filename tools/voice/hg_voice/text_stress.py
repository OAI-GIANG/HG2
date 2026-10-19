#!/usr/bin/env python3
"""Generate a deterministic, synthetic Vietnamese text-path stress suite.

This suite validates normalization/scoring/diagnostic behavior only. It does not
synthesize or recognize audio and cannot establish acoustic ASR quality.
"""
import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

from hg_voice.error_atlas import classify_difference
from hg_voice.metrics import score_pair, normalize_text

SEED = 20261018
SCHEMA = "hg2.vi-text-stress.v1"
CASES = [
    ("tone_mark", "ma", "má"),
    ("tone_mark", "ban", "bạn"),
    ("tone_mark", "thu", "thú"),
    ("tone_mark", "hoa", "hòa"),
    ("tone_mark", "nghi", "nghĩ"),
    ("unicode_composition", "hòa bình", "ho\u00e0 bình"),
    ("punctuation", "Xin chào!", "Xin chào"),
    ("punctuation", "Đúng rồi.", "Đúng rồi"),
    ("whitespace", "xin chào bạn", "xin  chào bạn"),
    ("token_boundary", "thành phố", "thànhphố"),
    ("digit_spelling", "mười hai", "12"),
    ("digit_spelling", "hai nghìn không trăm", "2000"),
    ("place_name", "Thành phố Thanh Hóa", "Thành phố Thanh Hoá"),
    ("proper_name", "Đỗ Quốc Oai", "Đỗ Quốc Oài"),
    ("code_switch", "mở ứng dụng settings", "mở ứng dụng cài đặt"),
    ("lexical_near_miss", "bàn ghế mới", "bàn chế mới"),
    ("word_order", "tôi sẽ đến ngày mai", "ngày mai tôi sẽ đến"),
    ("deletion", "xin chào mọi người", "xin mọi người"),
    ("insertion", "tôi đồng ý", "tôi hoàn toàn đồng ý"),
    ("empty_hypothesis", "đây là thử nghiệm", ""),
    ("empty_reference", "", "xin chào"),
    ("exact", "Việt Nam", "Việt Nam"),
    ("casefold", "XIN CHÀO", "xin chào"),
    ("unicode_combining", "Tôi yêu Việt Nam", "To\u0302i ye\u0302u Vie\u0323t Nam"),
    ("numbers_and_units", "năm ki lô mét", "5 km"),
    ("homophone_context", "sửa máy", "sữa máy"),
    ("homophone_context", "chuyện trò", "chuyền trò"),
    ("sentence_boundary", "xin chào. bạn khỏe không?", "xin chào bạn khỏe không"),
    ("regional_spelling", "nghỉ ngơi", "nghĩ ngơi"),
    ("long_context", "hôm nay tôi sẽ kiểm tra hệ thống nhận dạng tiếng Việt", "hôm nay tôi kiểm tra hệ thống nhận dạng tiếng Việt"),
]


def create_rows(seed=SEED):
    """Return stable case order and deterministic case IDs."""
    rng = random.Random(seed)
    rows = []
    order = list(range(len(CASES)))
    rng.shuffle(order)
    # Stable but seed-driven order lets experiments change seed transparently.
    for index in order:
        category, reference, hypothesis = CASES[index]
        # Apply scoring normalization so canonically equivalent Unicode is not an error.
        reference, hypothesis = normalize_text(reference), normalize_text(hypothesis)
        canonical = json.dumps(
            {"category": category, "reference": reference, "hypothesis": hypothesis},
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
        rows.append({
            "case_id": "vi-text-%03d" % (index + 1),
            "category": category,
            "reference": reference,
            "hypothesis": hypothesis,
            "case_sha256": hashlib.sha256(canonical).hexdigest(),
        })
    return rows


def evaluate(rows):
    category_totals = {}
    overall = {"cases": len(rows), "word_errors": 0, "reference_words": 0,
               "character_errors": 0, "reference_characters": 0}
    difference_counts = {}
    for row in rows:
        score = score_pair(row["reference"], row["hypothesis"])
        category = row["category"]
        bucket = category_totals.setdefault(category, {
            "cases": 0, "word_errors": 0, "reference_words": 0,
            "character_errors": 0, "reference_characters": 0,
        })
        bucket["cases"] += 1
        for key in ("word_errors", "reference_words", "character_errors", "reference_characters"):
            bucket[key] += score[key]
            overall[key] += score[key]
        observed = classify_difference(row["reference"], row["hypothesis"])
        difference_counts[observed] = difference_counts.get(observed, 0) + 1

    def rates(bucket):
        return {
            **bucket,
            "wer": bucket["word_errors"] / bucket["reference_words"] if bucket["reference_words"] else None,
            "cer": bucket["character_errors"] / bucket["reference_characters"] if bucket["reference_characters"] else None,
        }

    return {
        "schema_version": SCHEMA,
        "seed": SEED,
        "scope": "synthetic_text_path_only_not_audio_or_asr_quality",
        "status": "DIAGNOSTIC_ONLY_NOT_ACCEPTANCE",
        "case_count": len(rows),
        "overall": rates(overall),
        "by_category": {name: rates(value) for name, value in sorted(category_totals.items())},
        "observed_difference_classes": dict(sorted(difference_counts.items())),
        "known_limitations": [
            "No audio is generated or processed.",
            "Cases are hand-authored synthetic strings, not a representative sample.",
            "Numbers, names, dialect, homophone and code-switch cases need human review before interpreting as linguistic benchmarks.",
            "Metrics validate the text scoring path only; no inference about acoustic model quality is valid.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write JSON report; stdout by default")
    parser.add_argument("--jsonl", type=Path, help="write synthetic pairs as JSONL")
    args = parser.parse_args(argv)
    rows = create_rows()
    report = evaluate(rows)
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    if args.jsonl:
        args.jsonl.write_text("".join(
            json.dumps({k: row[k] for k in ("reference", "hypothesis")}, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
