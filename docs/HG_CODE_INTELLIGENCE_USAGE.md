# HG Code Intelligence V1 — Local Usage

Status: feature-candidate only; not wired into HG phone runtime.

## Run a read-only scan

From a local checkout of the isolated feature branch:

```sh
python3 -B tools/hg_code_intelligence.py \
  --repo /absolute/path/to/repository \
  --revision <caller-declared-commit-or-UNKNOWN> \
  --changed path/to/changed.py
```

The command prints a JSON report. It does not execute the analyzed repository, install packages, or access the network. By default it does not write a report file. If `--output` is specified, the target must be outside the analyzed repository root.

## What the report can say

- Which recognized source files were hashed and which Python files parsed.
- Which Python import statements resolve exactly to a local Python module.
- Known reverse dependents among these resolved static Python imports.
- Which source files were unsupported, skipped for size, or failed to parse.
- Which regular non-secret files have an unrecognized extension/name (`UNCLASSIFIED_FILE_TYPE`) and whether their bytes were hashed into the snapshot.
- Counts of excluded secret-shaped files and skipped symlinks; either condition forces coverage incomplete.
- A deterministic snapshot/report digest and whether two reports are stale relative to each other.

## What the report cannot say

It is not a full code graph, semantic call graph, proof of runtime behavior, or complete patch-impact report. Dynamic imports, reflection, build-generated relations and non-Python language dependencies are not resolved. The presence of non-Python sources, unclassified files, skipped files, excluded secret-shaped files, skipped symlinks, parsing failures or dynamic import sites forces `coverage_complete_for_all_repository_source` to false. The analyzer does not silently interpret an unknown extension as non-source. A true value is scoped to the discovered, non-excluded filesystem entries and this limited analyzer; it does not prove runtime dependencies or content hidden in excluded directories were discovered.

The revision field is caller-declared, not independently authenticated. A SHA-256 digest gives byte identity relative to the scanned files, not source authenticity, licensing or semantic correctness. Unknown source revision must stay `UNKNOWN` and must not be described as verified.

## Resource and privacy boundaries

Defaults: at most 20,000 filesystem entries, 4 MiB per recognized source file or hashed unclassified file, and 128 MiB total indexed bytes. Symlinks are not followed. Common generated directories and secret-shaped paths are excluded, and these exclusions force coverage incomplete. Hard resource-limit failures return no partial report. Review the policy against the repository in scope before relying on the output.

## Release gate

Do not use this candidate as release evidence, merge it into `hg-genesis`, or wire it into the phone runtime until a versioned ground-truth benchmark is frozen, run against representative repositories, scored under pre-registered thresholds, and all required gates pass. Unit tests validate the implementation contract but do not prove broad impact-analysis quality.
