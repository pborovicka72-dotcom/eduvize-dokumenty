"""Validate opaque central sessions without sharing the original administration key."""
import httpx
from fastapi import HTTPException
CENTRAL='https://eduvize-design-system-api.onrender.com'
async def central_admin(authorization,scope='documents'):
 if not authorization or not authorization.startswith('Bearer edu_'):return False
 try:
  async with httpx.AsyncClient(timeout=15,follow_redirects=False) as client:
   response=await client.get(CENTRAL+'/api/admin-session/validate',params={'scope':scope},headers={'Authorization':authorization})
 except httpx.HTTPError:raise HTTPException(503,'Přihlášení nyní nelze ověřit. Zkuste to znovu.')
 if response.status_code in (401,403):raise HTTPException(response.status_code,'Přihlášení vypršelo nebo chybí oprávnění. Otevřete rozcestník Eduvize.')
 if not response.is_success:raise HTTPException(503,'Centrum přihlášení nyní není dostupné.')
 try:data=response.json()
 except ValueError:raise HTTPException(503,'Centrum přihlášení vrátilo neplatnou odpověď.')
 if data.get('valid') is not True or data.get('scope')!=scope:raise HTTPException(401,'Neplatné přihlášení.')
 return True
