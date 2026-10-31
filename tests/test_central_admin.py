import sys,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock,AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import central_admin
from fastapi import HTTPException
class CentralAdminTests(unittest.IsolatedAsyncioTestCase):
 def response(self,status=200,data=None):
  response=MagicMock();response.status_code=status;response.is_success=status<300;response.json.return_value=data or {'valid':True,'scope':'documents'};return response
 async def test_raw_keys_stay_with_existing_validation(self):
  with patch.object(central_admin.httpx,'AsyncClient') as client:
   self.assertFalse(await central_admin.central_admin('Bearer old-api-key'));client.assert_not_called()
 async def test_valid_session_is_verified_for_documents_only(self):
  with patch.object(central_admin.httpx,'AsyncClient') as client:
   client.return_value.__aenter__.return_value.get.return_value=self.response()
   self.assertTrue(await central_admin.central_admin('Bearer edu_test'))
   self.assertEqual(client.return_value.__aenter__.return_value.get.call_args.kwargs['params'],{'scope':'documents'})
 async def test_revoked_session_and_service_failure_never_fall_back_to_raw_key(self):
  for status in [401,403,500]:
   with self.subTest(status=status),patch.object(central_admin.httpx,'AsyncClient') as client:
    client.return_value.__aenter__.return_value.get.return_value=self.response(status)
    with self.assertRaises(HTTPException):await central_admin.central_admin('Bearer edu_test')
 async def test_wrong_scope_is_rejected(self):
  with patch.object(central_admin.httpx,'AsyncClient') as client:
   client.return_value.__aenter__.return_value.get.return_value=self.response(data={'valid':True,'scope':'styles'})
   with self.assertRaises(HTTPException):await central_admin.central_admin('Bearer edu_test')
if __name__=='__main__':unittest.main()
