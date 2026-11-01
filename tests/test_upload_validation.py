import ast
from pathlib import Path
import unittest
from fastapi import HTTPException

source = ast.parse((Path(__file__).resolve().parents[1] / 'app.py').read_text())
module = ast.Module(body=[n for n in source.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'upload'], type_ignores=[])
module.body[0].decorator_list = []

class UploadValidationTest(unittest.IsolatedAsyncioTestCase):
    async def test_office_files_rejected_before_reading(self):
        types = next(n.value for n in source.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'TYPES' for t in n.targets))
        for ext in ['docx', 'pptx', 'doc', 'ppt']:
            with self.subTest(ext=ext):
                async def check_admin(_): pass
                class Upload:
                    filename = 'test.' + ext
                    async def read(self, limit): raise AssertionError('must reject before read')
                scope = dict(UploadFile=object, File=lambda *a:None, Form=lambda *a:None, Header=lambda **k:None,
                             check_admin=check_admin, document_scope=lambda _:None, Path=Path,
                             TYPES=ast.literal_eval(types), HTTPException=HTTPException)
                exec(compile(module, 'upload', 'exec'), scope)
                with self.assertRaises(HTTPException) as caught:
                    await scope['upload'](Upload(), authorization='test')
                self.assertEqual(caught.exception.status_code, 415)
                self.assertIn('PDF', caught.exception.detail)

if __name__ == '__main__': unittest.main()
