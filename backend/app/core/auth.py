"""Domain API role dependencies over the server-side OIDC session."""
from fastapi import Depends,HTTPException,Request
from app.core.session_auth import require_user

LEVELS={'viewer':1,'operator':2,'admin':3}

async def get_current_user(request:Request):
    session=require_user(request)
    roles=['operator' if role=='reviewer' else role for role in session['roles']]
    role=max(roles,key=lambda r:LEVELS.get(r,0),default='viewer')
    return {'sub':session['subject'],'name':session['username'],'role':role,'roles':roles}

def require_role(minimum_role):
    async def check(user=Depends(get_current_user)):
        if LEVELS.get(user['role'],0)<LEVELS[minimum_role]:raise HTTPException(403,'Insufficient role')
        return user
    return check
