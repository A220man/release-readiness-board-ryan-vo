"""Consent-gated advice; network calls never hold the database transaction."""
from typing import Literal
from pydantic import BaseModel
from fastapi import APIRouter,Depends,HTTPException
from app.core.auth import require_role
from app.core.database import get_database_manager
from app.services.release_service import ReleaseService
from app.services.blocker_service import BlockerService
from app.services.invariants import current_decisions
from app.services.llm_service import llm_service

router=APIRouter(prefix='/api/llm',tags=['llm'])
class Consent(BaseModel):consent:Literal[True]

@router.post('/analyze/{release_id}')
async def analyze_release(release_id:str,body:Consent,user=Depends(require_role('operator'))):
    manager=await get_database_manager()
    async with manager.get_connection() as db:
        try:r=await ReleaseService(db).get_release(release_id)
        except ValueError as exc:raise HTTPException(404,str(exc))
        decisions=await current_decisions(db,release_id)
        data={k:r[k] for k in ['name','version','status','revision','criteria_summary','blocker_summary','risk_score']}
        data['current_decision_counts']={d:sum(a['decision']==d for a in decisions) for d in ['approved','rejected','conditional']}
    result=await llm_service.analyze_release_risks(data)
    return result or {'analysis':'No model is configured. Deterministic risk assessment remains available.','suggestions':[],'confidence':'','advisory':'No data was sent to a provider.','provider':''}

@router.post('/summarize-blockers/{release_id}')
async def summarize_blockers(release_id:str,body:Consent,user=Depends(require_role('operator'))):
    manager=await get_database_manager()
    async with manager.get_connection() as db:
        try:await ReleaseService(db).get_release(release_id)
        except ValueError as exc:raise HTTPException(404,str(exc))
        records=await BlockerService(db).list_blockers(release_id)
        data=[{k:b[k] for k in ['title','description','severity','status','category']} for b in records]
    result=await llm_service.summarize_blockers(data)
    return {'summary':result or 'No model is configured. Use deterministic blocker classification.','advisory':'Model suggestions are unverified and never change release state.'}
