import sys,types,unittest
from contextvars import ContextVar
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
# Isolate pure scheduler rules from unrelated account database initialization.
sys.modules.setdefault("school_accounts",types.SimpleNamespace(school_context=ContextVar("school",default=None),LEGACY_PROFILE="0"*32))
from update_plans import next_due,validate,update_plan_router,school_context
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi import HTTPException
class PlansTest(unittest.TestCase):
 def test_quarter_and_disabled(self):
  self.assertEqual(next_due("quarterly","2026-11-03T08:00:00+01:00"),"2027-01-01T09:00:00+01:00")
  self.assertIsNone(next_due("off","2026-11-03T08:00:00Z"))
 def test_clock_and_dst(self):
  self.assertEqual(next_due("weekly","2027-03-27T12:00:00+01:00"),"2027-03-29T09:00:00+02:00")
  self.assertEqual(next_due("monthly","2027-01-01T09:00:00+01:00"),"2027-02-01T09:00:00+01:00")
 def test_auth_and_tenant(self):
  class Store:
   def read(self,school,app):return {"school":school,"app":app}
   def maintenance(self):return {"items":[]}
  class Accounts:
   def public_profile(self,profile):return {"id":"public-school"}
  async def authorize(token):
   if token!="Bearer test":raise HTTPException(401,"Přihlaste se")
   school_context.set({"id":"signed-school"})
  app=FastAPI();app.include_router(update_plan_router(Store(),authorize,Accounts()))
  with TestClient(app) as client:
   self.assertEqual(client.get("/api/admin/update-plans/holidays").status_code,401)
   result=client.get("/api/admin/update-plans/holidays",headers={"Authorization":"Bearer test"})
   self.assertEqual(result.json()["school"],"signed-school")
   self.assertEqual(result.headers["cache-control"],"no-store")
   self.assertEqual(client.get("/api/update-plans/holidays?profile="+"a"*32).json()["school"],"public-school")
   self.assertEqual(client.get("/api/update-plans/maintenance").json(),{"items":[]})
 def test_invalid(self):
  for change in [{"refreshSeconds":-1},{"maintenanceFrequency":"minutely"},{"refreshSeconds":True},{"expectedRevision":None}]:
   with self.assertRaises(HTTPException):validate(dict({"refreshSeconds":None,"maintenanceFrequency":"quarterly","expectedRevision":0},**change))
if __name__=="__main__":unittest.main()
