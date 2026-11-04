"""Protocol tests with a transactional in-memory database double; production uses PostgreSQL."""
import copy, json, unittest
from contextlib import contextmanager
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import kiosk_remote as remote

class Result:
    def __init__(self,value=None):self.value=value
    def fetchone(self):return self.value
class Database:
    def __init__(self):self.rows={}
    def execute(self,sql,args=()):
        if sql.startswith('DELETE'):
            self.rows={k:v for k,v in self.rows.items() if v[1]>=args[0]}
        elif sql.startswith('SELECT count'):return Result((len(self.rows),))
        elif sql.startswith('INSERT'):self.rows[args[0]]=(json.loads(args[2]),args[1])
        elif sql.startswith('SELECT id'):
            found=next(((sid,d,expires) for sid,(d,expires) in self.rows.items() if d.get('pairCode')==args[0] and expires>args[1] and d['pairUntil']>args[2]),None)
            if found:return Result(copy.deepcopy((found[0],found[1]) if sql.startswith('SELECT id,data') else (found[0],)))
        elif sql.startswith('SELECT data'):
            return Result(copy.deepcopy(self.rows.get(args[0])))
        elif sql.startswith('UPDATE'):self.rows[args[2]]=(json.loads(args[0]),args[1])
        return Result()
class Tests(unittest.TestCase):
    def setUp(self):
        self.clock=1000.;self.db=Database();self.store=remote.RemoteStore('test')
        @contextmanager
        def transaction():yield self.db
        self.store.transaction=transaction
        self.time=patch.object(remote.time,'time',lambda:self.clock);self.time.start();self.addCleanup(self.time.stop)
        self.snapshot={'title':'Školní kiosek','revision':'r1','items':[{'id':'home','label':'Domů','active':False},{'id':'tile:0','label':'O škole','active':False}]}
        self.session=self.store.create(self.snapshot);self.sid=self.session['id'];self.owner='Bearer '+self.session['owner']
    def heartbeat(self,ack=0):return self.store.update(self.sid,'owner',self.owner,'heartbeat',{'snapshot':self.snapshot,'ack':ack})
    def join(self):
        pair=self.heartbeat()['pairToken'];value=self.store.update(self.sid,'pair','Bearer '+pair,'join');return 'Bearer '+value['controller']
    def test_pair_command_ack_and_replay(self):
        controller=self.join();self.assertTrue(self.heartbeat()['connected'])
        command={'id':'tile:0','revision':'r1','requestId':'12345678-12345678'}
        self.store.update(self.sid,'controller',controller,'command',command)
        self.store.update(self.sid,'controller',controller,'command',command)
        commands=self.heartbeat()['commands'];self.assertEqual(len(commands),1);self.assertEqual(commands[0]['id'],'tile:0')
        self.assertEqual(self.heartbeat(commands[0]['sequence'])['commands'],[])
    def test_qr_contains_fragment_not_admin_credentials(self):
        qr=self.store.qr(self.sid,self.owner);self.assertIn(b'<svg',qr);self.assertNotIn(self.session['owner'].encode(),qr)
    def test_owner_isolation_and_stale_menu(self):
        with self.assertRaises(HTTPException) as e:self.store.update(self.sid,'owner','Bearer invalid','heartbeat',{})
        self.assertEqual(e.exception.status_code,401)
        controller=self.join()
        for identifier,revision in [('https://evil.test','r1'),('tile:0','old')]:
            with self.assertRaises(HTTPException) as e:self.store.update(self.sid,'controller',controller,'command',{'id':identifier,'revision':revision,'requestId':'12345678-12345678'})
            self.assertEqual(e.exception.status_code,409)
    def test_exclusive_pair_and_idle_expiry(self):
        pair=self.heartbeat()['pairToken'];controller=self.join()
        with self.assertRaises(HTTPException):self.store.update(self.sid,'pair','Bearer '+pair,'join')
        for _ in range(5):self.clock+=25;self.heartbeat()
        with self.assertRaises(HTTPException) as e:self.store.update(self.sid,'controller',controller,'state')
        self.assertEqual(e.exception.status_code,401)
        self.assertNotEqual(pair,self.heartbeat()['pairToken'])
    def test_offline_commands_expire(self):
        controller=self.join();self.store.update(self.sid,'controller',controller,'command',{'id':'home','revision':'r1','requestId':'12345678-12345678'})
        self.clock+=6;self.assertEqual(self.heartbeat()['commands'],[])
        self.clock+=21
        with self.assertRaises(HTTPException) as e:self.store.update(self.sid,'controller',controller,'state')
        self.assertEqual(e.exception.status_code,410)
    def test_disconnect_revokes_and_rotates(self):
        controller=self.join();self.store.update(self.sid,'owner',self.owner,'disconnect');self.assertFalse(self.heartbeat()['connected'])
        with self.assertRaises(HTTPException):self.store.update(self.sid,'controller',controller,'state')
    def test_manual_pair_consumes_qr_and_code(self):
        pair=self.heartbeat()
        self.assertRegex(pair['pairCode'],r'^[0-9]{8}$')
        joined=self.store.join_code(pair['pairCode'])
        self.assertEqual(joined['session'],self.sid)
        self.assertNotIn('owner',joined)
        self.assertEqual(joined['snapshot'],self.snapshot)
        self.assertIsNone(self.heartbeat()['pairCode'])
        with self.assertRaises(HTTPException):self.store.join_code(pair['pairCode'])
        with self.assertRaises(HTTPException):self.store.update(self.sid,'pair','Bearer '+pair['pairToken'],'join')
        self.store.update(self.sid,'controller','Bearer '+joined['controller'],'leave')
        self.assertNotEqual(pair['pairCode'],self.heartbeat()['pairCode'])
    def test_qr_pair_consumes_manual_code(self):
        code=self.heartbeat()['pairCode'];self.join()
        with self.assertRaises(HTTPException):self.store.join_code(code)
    def test_manual_code_rejects_offline_expired_and_rotated_sessions(self):
        code=self.heartbeat()['pairCode'];self.clock+=21
        with self.assertRaises(HTTPException):self.store.join_code(code)
        for _ in range(5):self.clock+=25;self.heartbeat()
        with self.assertRaises(HTTPException):self.store.join_code(code)
        self.assertNotEqual(code,self.heartbeat()['pairCode'])
    def test_live_codes_are_unique_even_when_random_collides(self):
        code=self.heartbeat()['pairCode']
        other='00000000' if code!='00000000' else '00000001'
        with patch.object(remote.secrets,'randbelow',side_effect=[int(code),int(other)]):
            created=self.store.create(self.snapshot)
        self.assertEqual(self.db.rows[created['id']][0]['pairCode'],other)
    def test_manual_pair_http_validation_and_attempt_limit(self):
        with patch.object(remote,'RemoteStore',return_value=self.store):
            app=FastAPI();app.include_router(remote.remote_router('test'));client=TestClient(app)
            self.assertEqual(client.post('/api/kiosk-remote/join-code',json={'code':'short'}).status_code,422)
            response=client.post('/api/kiosk-remote/join-code',json={'code':self.heartbeat()['pairCode']})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['cache-control'],'no-store')
            for _ in range(4):self.assertEqual(client.post('/api/kiosk-remote/join-code',json={'code':'12345678'}).status_code,410)
            self.assertEqual(client.post('/api/kiosk-remote/join-code',json={'code':'12345678'}).status_code,429)
    def test_http_schema_and_limits(self):
        with patch.object(remote,'RemoteStore',return_value=self.store):
            app=FastAPI();app.include_router(remote.remote_router('test'));client=TestClient(app)
            for _ in range(10):self.assertEqual(client.post('/api/kiosk-remote/sessions',json=self.snapshot).status_code,200)
            self.assertEqual(client.post('/api/kiosk-remote/sessions',json=self.snapshot).status_code,429)
            bad={**self.snapshot,'items':[{'id':'https://evil.test','label':'X'}]}
            self.assertEqual(client.post('/api/kiosk-remote/sessions',json=bad).status_code,422)
            self.assertEqual(client.get('/api/kiosk-remote/sessions/'+self.sid+'/state').status_code,401)
if __name__=='__main__':unittest.main()

