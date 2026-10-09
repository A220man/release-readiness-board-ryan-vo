import pytest
import pytest_asyncio
from app.core.database import DatabaseManager
from app.services.release_service import ReleaseService
from app.services.criteria_service import CriteriaService
from app.services.approval_service import ApprovalService
from app.services.audit_service import AuditService

@pytest_asyncio.fixture
async def manager(tmp_path):
    m=DatabaseManager(str(tmp_path/'test.db'));await m.connect();await m.init_db()
    yield m
    await m.close()

async def create(db):
    return await ReleaseService(db).create_release({'name':'Release QA','version':'1.0.0'},'creator','operator')

@pytest.mark.asyncio
async def test_cannot_approve_without_criteria_or_decision(manager):
    async with manager.get_connection() as db:
        r=await create(db);svc=ReleaseService(db)
        await svc.transition_release(r['id'],'in_review','creator','operator')
        with pytest.raises(ValueError):await svc.transition_release(r['id'],'approved','admin','admin')

@pytest.mark.asyncio
async def test_audit_failure_rolls_back_creation(manager,monkeypatch):
    async def fail(*args,**kwargs):raise RuntimeError('injected audit write failure')
    monkeypatch.setattr(AuditService,'log_action',fail)
    with pytest.raises(RuntimeError):
        async with manager.get_connection() as db:await create(db)
    async with manager.get_connection() as db:
        row=await (await db.execute('SELECT COUNT(*) FROM releases')).fetchone()
        assert row[0]==0

@pytest.mark.asyncio
async def test_creator_cannot_approve_own_release(manager):
    async with manager.get_connection() as db:
        r=await create(db);await ReleaseService(db).transition_release(r['id'],'in_review','creator','operator')
        with pytest.raises(ValueError):await ApprovalService(db).create_approval({'release_id':r['id'],'decision':'approved'},'creator','admin')

@pytest.mark.asyncio
async def test_review_pass_requires_evidence(manager):
    async with manager.get_connection() as db:
        r=await create(db);svc=CriteriaService(db)
        item=await svc.add_criterion({'release_id':r['id'],'name':'Tests','category':'testing'},'creator','operator')
        with pytest.raises(ValueError):await svc.review_criterion(item['id'],'reviewer','passed','reviewer','operator')

async def ready(db):
    r=await create(db);criteria=CriteriaService(db)
    c=await criteria.add_criterion({'release_id':r['id'],'name':'Regression suite','category':'testing'},'creator','operator')
    await criteria.update_criterion(c['id'],{'evidence':'Regression suite: 48 passed, revision abc123'},'creator','operator')
    await criteria.review_criterion(c['id'],'reviewer','passed','reviewer','operator')
    await ReleaseService(db).transition_release(r['id'],'in_review','creator','operator')
    await ApprovalService(db).create_approval({'release_id':r['id'],'decision':'approved','comment':'Reviewed the retained evidence'},'reviewer','operator')
    return r,c

@pytest.mark.asyncio
async def test_evidence_edit_invalidates_approval(manager):
    async with manager.get_connection() as db:
        r,c=await ready(db)
        await CriteriaService(db).update_criterion(c['id'],{'evidence':'Different regression evidence'},'creator','operator')
        await CriteriaService(db).review_criterion(c['id'],'reviewer','passed','reviewer','operator')
        with pytest.raises(ValueError,match='current evidence revision'):
            await ReleaseService(db).transition_release(r['id'],'approved','admin','admin')

@pytest.mark.asyncio
async def test_valid_release_and_frozen_evidence(manager):
    async with manager.get_connection() as db:
        r,c=await ready(db);svc=ReleaseService(db)
        assert (await svc.transition_release(r['id'],'approved','admin','admin'))['status']=='approved'
        with pytest.raises(ValueError,match='frozen'):
            await CriteriaService(db).update_criterion(c['id'],{'evidence':'Replacement evidence'},'creator','operator')
        assert (await svc.transition_release(r['id'],'released','admin','admin'))['status']=='released'
        with pytest.raises(ValueError):await svc.delete_release(r['id'],'admin','admin')

@pytest.mark.asyncio
async def test_latest_rejection_blocks_prior_approval(manager):
    async with manager.get_connection() as db:
        r,c=await ready(db)
        await ApprovalService(db).create_approval({'release_id':r['id'],'decision':'rejected','comment':'New concern'},'reviewer','operator')
        with pytest.raises(ValueError,match='rejection'):
            await ReleaseService(db).transition_release(r['id'],'approved','admin','admin')

@pytest.mark.asyncio
async def test_revocation_reopens_approved_release(manager):
    async with manager.get_connection() as db:
        r,c=await ready(db);svc=ReleaseService(db);approvals=ApprovalService(db)
        await svc.transition_release(r['id'],'approved','admin','admin')
        approval=(await approvals.list_approvals(r['id']))[0]
        await approvals.revoke_approval(approval['id'],'admin','admin')
        assert (await svc.get_release(r['id']))['status']=='in_review'
