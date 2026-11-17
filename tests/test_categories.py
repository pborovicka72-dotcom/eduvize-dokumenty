import ast
import unittest
from pathlib import Path

from fastapi import HTTPException

source = ast.parse((Path(__file__).resolve().parents[1] / "app.py").read_text())
names = {"category_names", "in_document_scope", "rename_category_data", "delete_category_data"}
module = ast.Module(body=[node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
scope = {"HTTPException": HTTPException, "DEFAULT_CATEGORIES": ["Ostatní"]}
exec(compile(module, "categories", "exec"), scope)


class CategoryManagementTest(unittest.TestCase):
    def setUp(self):
        self.data = {
            "items": [{"id": "one", "category": "Výlety", "scope": "documents"}],
            "categories": ["Výlety", "Archiv"],
            "hidden_categories": ["Výlety"],
        }

    def test_rename_updates_documents_and_visibility(self):
        items, categories, hidden = scope["rename_category_data"](self.data, "Výlety", "Exkurze")
        self.assertEqual(items[0]["category"], "Exkurze")
        self.assertEqual(categories, ["Exkurze", "Archiv"])
        self.assertEqual(hidden, ["Exkurze"])

    def test_delete_requires_explicit_destination_for_documents(self):
        with self.assertRaises(HTTPException):
            scope["delete_category_data"](self.data, "Výlety")
        items, categories, hidden, moved = scope["delete_category_data"](self.data, "Výlety", "Ostatní")
        self.assertEqual((items[0]["category"], categories, hidden, moved), ("Ostatní", ["Archiv"], [], 1))

    def test_default_category_cannot_be_renamed_or_deleted(self):
        for operation in (lambda: scope["rename_category_data"](self.data, "Ostatní", "Nová"),
                          lambda: scope["delete_category_data"](self.data, "Ostatní")):
            with self.assertRaises(HTTPException):
                operation()


if __name__ == "__main__":
    unittest.main()
