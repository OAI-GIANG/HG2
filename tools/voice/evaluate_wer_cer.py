#!/usr/bin/env python3
"""Score a JSONL file of approved reference/hypothesis text pairs; no audio or network access."""
import argparse
import json
import sys
import hashlib
from pathlib import Path
from hg_voice.metrics import score_pair
from hg_voice.error_atlas import classify_difference


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path, help="UTF-8 JSONL: one object with reference and hypothesis per line")
    args = parser.parse_args(argv)
    atlas_counts = {}
    input_hash = hashlib.sha256()
    totals = {"utterances": 0, "reference_words": 0, "word_errors": 0,
              "reference_characters": 0, "character_errors": 0, "empty_references": 0}
    try:
        with args.jsonl.open("rb") as raw_stream:
            raw_bytes = raw_stream.read()
        input_hash.update(raw_bytes)
        decoded = raw_bytes.decode("utf-8")
        for line_no, line in enumerate(decoded.splitlines(), 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_no}: invalid JSON: {exc.msg}") from exc
            if not isinstance(item, dict) or not isinstance(item.get("reference"), str) or not isinstance(item.get("hypothesis"), str):
                raise ValueError(f"line {line_no}: expected string fields reference and hypothesis")
            result = score_pair(item["reference"], item["hypothesis"])
            category = classify_difference(item["reference"], item["hypothesis"])
            atlas_counts[category] = atlas_counts.get(category, 0) + 1
            totals["utterances"] += 1
            totals["reference_words"] += result["reference_words"]
            totals["word_errors"] += result["word_errors"]
            totals["reference_characters"] += result["reference_characters"]
            totals["character_errors"] += result["character_errors"]
            totals["empty_references"] += result["wer"] is None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    if totals["utterances"] == 0:
        print(json.dumps({"status": "ERROR", "error": "no scored utterances"}), file=sys.stderr)
        return 2
    totals["wer"] = totals["word_errors"] / totals["reference_words"] if totals["reference_words"] else None
    totals["cer"] = totals["character_errors"] / totals["reference_characters"] if totals["reference_characters"] else None
    totals["error_atlas"] = {name: {"count": count, "denominator": totals["utterances"],
                                     "rate": count / totals["utterances"]}
                             for name, count in sorted(atlas_counts.items())}
    totals["error_atlas_scope"] = "observable_text_difference_not_acoustic_causality"
    totals["status"] = "SCORED_NOT_ACCEPTANCE"
    totals["input_sha256"] = input_hash.hexdigest()
    totals["input_format"] = "UTF-8 JSONL raw bytes; blank lines ignored for scoring but included in hash"
    totals["scoring_policy"] = "NFC + casefold + collapsed whitespace; punctuation retained; aggregate denominators exclude empty-reference units"
    print(json.dumps(totals, ensure_ascii=False, sort_keys=True, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
