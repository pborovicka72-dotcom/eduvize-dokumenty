"""Isolated SQL test shim; no network or school data."""
import sqlite3
class EmptyCursor:
    def fetchone(self):return None
    def fetchall(self):return []
class Connection:
    def __init__(self,path):self.conn=sqlite3.connect(path)
    def execute(self,sql,args=()):
        if 'pg_advisory_xact_lock' in sql:return EmptyCursor()
        if 'to_regclass' in sql:
            row=self.conn.execute("SELECT name FROM sqlite_master WHERE name=?",args).fetchone()
            return self.conn.execute('SELECT ?', (row[0] if row else None,))
        return self.conn.execute(sql.replace('%s','?'),args)
    def __enter__(self):return self
    def __exit__(self,typ,*args):
        if typ:self.conn.rollback()
        else:self.conn.commit()
        self.conn.close()
