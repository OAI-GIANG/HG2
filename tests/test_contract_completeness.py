import hashlib, json, subprocess, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


class ContractCompletenessTests(unittest.TestCase):
    def test_manifest_names_real_modules(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        for module in manifest["modules"]:
            path = ROOT.joinpath(*module.split(".")).with_suffix(".py")
            with self.subTest(module=module): self.assertTrue(path.is_file(), str(path))

    def test_acceptance_matrix_has_required_domains_and_states(self):
        matrix = (ROOT / "contract" / "ACCEPTANCE_MATRIX_V1.md").read_text(encoding="utf-8")
        lowered = matrix.lower()
        for text in ("provider", "tool orchestration", "authorization", "bounded", "audit", "provenance"):
            with self.subTest(text=text): self.assertIn(text, lowered)
        for text in ("IMPLEMENTED_AND_TESTED", "IMPLEMENTED_UNVERIFIED", "MISSING", "DEFECTIVE"):
            with self.subTest(text=text): self.assertIn(text, matrix)

    def test_tool_registry_excludes_dangerous_capabilities(self):
        from hg.toolplane import _TOOL_SCHEMAS
        names = {entry["function"]["name"] for entry in _TOOL_SCHEMAS}
        self.assertEqual(names, {"identity.get", "history.verify", "history.summary", "history.recent", "session.create"})
        self.assertFalse(names & {"shell.exec", "file.read", "file.write", "network.fetch", "deploy"})

    def test_provenance_graph_hashes_match_files(self):
        graph = json.loads((ROOT / "provenance" / "HG2_SOURCE_PROVENANCE_GRAPH_V1.json").read_text(encoding="utf-8"))
        self.assertEqual(graph["repository"], "OAI-GIANG/HG2")
        self.assertEqual(graph["claim_level"], "CONTENT_HASH_INTEGRITY_ONLY")
        self.assertTrue(graph["nodes"])
        seen = set()
        for node in graph["nodes"]:
            rel = node["path"]
            self.assertNotEqual(rel, "provenance/HG2_SOURCE_PROVENANCE_GRAPH_V1.json")
            self.assertNotIn(rel, seen)
            seen.add(rel)
            target = ROOT / rel
            self.assertTrue(target.is_file(), rel)
            raw = target.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), node["sha256"], rel)
            git_blob = subprocess.check_output(["git", "hash-object", rel], cwd=ROOT, text=True).strip()
            self.assertEqual(git_blob, node["git_blob_sha"], rel)


if __name__ == "__main__":
    unittest.main()
