"""Content checks, no model needed.

    .venv/bin/python -m unittest discover -s tests -v
"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import content  # noqa: E402


class RealContent(unittest.TestCase):
    def test_everything_loads(self):
        content.validate_all()
        self.assertEqual(len(content.client_ids()), 4)
        self.assertGreaterEqual(len(content.load_catalogue()["products"]), 3)

    def test_public_client_has_no_hidden_fields(self):
        for cid in content.client_ids():
            client = content.load_client(cid)
            public = content.public_client(client)
            for key in ("hidden_needs", "suitable_products", "unsuitable_products", "persona"):
                self.assertNotIn(key, public)
            text = str(public)
            for n in client["hidden_needs"]:
                self.assertNotIn(n["fact"].strip()[:40], text)

    def test_closed_needs_never_reach_the_client_prompt(self):
        for cid in content.client_ids():
            client = content.load_client(cid)
            prompt = content.client_system_prompt(client, opened=[])
            for n in client["hidden_needs"]:
                self.assertNotIn(n["fact"].strip()[:40], prompt, f"{cid}/{n['id']} fact leaked")
                self.assertNotIn(n["label"], prompt, f"{cid}/{n['id']} label leaked")

    def test_opened_need_is_in_the_client_prompt(self):
        client = content.load_client("khalid")
        need = client["hidden_needs"][0]
        prompt = content.client_system_prompt(client, opened=[need["id"]], answer_now=need["id"])
        self.assertIn(need["fact"].strip()[:40], prompt)


class BrokenContent(unittest.TestCase):
    """Each broken edit must raise ContentError naming the file, never a raw Python error."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(content.CONTENT, self.tmp / "content")
        shutil.copytree(content.PROMPTS, self.tmp / "prompts")
        self.saved = (content.ROOT, content.CONTENT, content.PROMPTS)
        content.ROOT, content.CONTENT, content.PROMPTS = self.tmp, self.tmp / "content", self.tmp / "prompts"

    def tearDown(self):
        content.ROOT, content.CONTENT, content.PROMPTS = self.saved
        shutil.rmtree(self.tmp)

    def edit(self, rel, old, new):
        p = self.tmp / "content" / rel
        text = p.read_text()
        self.assertIn(old, text)
        p.write_text(text.replace(old, new, 1))

    def assertBroken(self, file_hint):
        with self.assertRaises(content.ContentError) as cm:
            content.validate_all()
        self.assertIn(file_hint, str(cm.exception))

    def test_bad_yaml(self):
        (self.tmp / "content/clients/khalid/hidden.yaml").write_text("hidden_needs: [\n")
        self.assertBroken("khalid/hidden.yaml")

    def test_unknown_product(self):
        self.edit("clients/khalid/hidden.yaml", "suitable_products: [islamic-receivables]", "suitable_products: [nope]")
        self.assertBroken("khalid/hidden.yaml")

    def test_duplicate_need_id(self):
        self.edit("clients/khalid/hidden.yaml", "id: payroll", "id: late-payments")
        self.assertBroken("khalid/hidden.yaml")

    def test_keywords_not_a_list(self):
        self.edit("clients/khalid/hidden.yaml", "keywords: [owe, owing, debt", "keywords: owe debt #[")
        self.assertBroken("khalid/hidden.yaml")

    def test_id_differs_from_folder(self):
        self.edit("clients/khalid/profile.yaml", "id: khalid", "id: kalid")
        self.assertBroken("khalid/profile.yaml")

    def test_bad_difficulty(self):
        self.edit("clients/khalid/profile.yaml", "difficulty: hard", "difficulty: tricky")
        self.assertBroken("khalid/profile.yaml")

    def test_missing_field(self):
        self.edit("clients/khalid/hidden.yaml", "    while_closed: Changes the subject back to the new contracts.\n", "")
        self.assertBroken("khalid/hidden.yaml")

    def test_bad_product_type(self):
        self.edit("products.yaml", "type: islamic", "type: halal")
        self.assertBroken("products.yaml")


if __name__ == "__main__":
    unittest.main()
