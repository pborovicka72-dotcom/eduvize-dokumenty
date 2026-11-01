import ast
import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

class StatusTests(unittest.TestCase):
    def status(self, valid=True):
        tree=ast.parse((Path(__file__).resolve().parents[1]/'app.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='status')
        node.decorator_list=[]
        for arg in node.args.args:arg.annotation=None
        check=AsyncMock(side_effect=None if valid else PermissionError('invalid key'))
        restore=Mock(side_effect=RuntimeError('token storage unavailable'))
        scope={'check_admin':check,'restore_tokens':restore,'Header':lambda **kw:kw.get('default')}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'status','exec'),scope)
        return scope['status'],check,restore
    def test_valid_key_can_sign_in_when_token_storage_is_down(self):
        status,check,restore=self.status()
        self.assertEqual(asyncio.run(status('Bearer test',authOnly=True)),{'authenticated':True})
        check.assert_awaited_once_with('Bearer test');restore.assert_not_called()
    def test_invalid_key_is_rejected_before_storage(self):
        status,check,restore=self.status(False)
        with self.assertRaises(PermissionError):asyncio.run(status('Bearer wrong',authOnly=True))
        restore.assert_not_called()
    def test_regular_status_still_checks_token_storage(self):
        status,check,restore=self.status()
        with self.assertRaises(RuntimeError):asyncio.run(status('Bearer test'))
        restore.assert_called_once()

if __name__=='__main__':unittest.main()
