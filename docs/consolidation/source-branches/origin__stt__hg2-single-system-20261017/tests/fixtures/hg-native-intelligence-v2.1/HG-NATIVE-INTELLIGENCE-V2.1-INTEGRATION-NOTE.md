# HG Native Intelligence V2.1 — HG2 integration note

- Package provenance: copied from the Termux-generated local `CP0-EXTERNAL-REFERENCE-IMPLEMENTATION/HG-NATIVE-INTELLIGENCE-FIXTURES-V2.1` package on 2026-10-17.
- Nature: synthetic fixture/oracle test data and package validators. These are not executable prompts to an HG runtime adapter; their oracle predicates are package-level declarations and selected arithmetic checks.
- Tests: 26 fixture records remain `NOT_RUN`; the integration tests ensure this status remains explicit, run the 12 package regression tests and run the static/semantic validator.
- Runtime acceptance is not established by these tests. A future authorized runtime adapter must map each fixture/predicate to actual invocations and evidence without rewriting oracle expectations after observing outputs.
- Historical source CP0's original 26 criteria remains unresolved; this package is not claimed as a replacement or authenticated transcription.
