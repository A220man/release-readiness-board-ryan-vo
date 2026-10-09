"""Release evidence boundaries, shared by every mutating service."""
from datetime import datetime,timezone

async def release_row(db,release_id):
    row=await (await db.execute('SELECT * FROM releases WHERE id=?',(release_id,))).fetchone()
    if row is None:raise ValueError('Release not found')
    return dict(row)

async def touch_release(db,release_id):
    row=await release_row(db,release_id)
    if row['status'] not in {'draft','in_review'}:
        raise ValueError('Release evidence is frozen; return the release to review before editing')
    await db.execute('UPDATE releases SET revision=revision+1,updated_at=? WHERE id=?',(datetime.now(timezone.utc).isoformat(),release_id))

async def current_decisions(db,release_id):
    row=await release_row(db,release_id)
    records=await (await db.execute('SELECT * FROM approvals WHERE release_id=? AND release_revision=? ORDER BY created_at DESC,rowid DESC',(release_id,row['revision']))).fetchall()
    latest={}
    for record in records:latest.setdefault(record['approver'],dict(record))
    return list(latest.values())

async def require_ready(db,release_id):
    row=await release_row(db,release_id)
    criteria=await (await db.execute('SELECT * FROM criteria WHERE release_id=? AND required=1',(release_id,))).fetchall()
    if not criteria:raise ValueError('At least one required criterion is needed for approval')
    if any(c['status']!='passed' or not c['evidence'].strip() or not c['reviewed_by'] for c in criteria):
        raise ValueError('Required criteria need passing reviews and evidence')
    blockers=await (await db.execute("SELECT * FROM blockers WHERE release_id=? AND status NOT IN ('resolved','accepted')",(release_id,))).fetchall()
    if blockers:raise ValueError('Unresolved blockers must be resolved or explicitly accepted')
    decisions=await current_decisions(db,release_id)
    if any(d['decision'] in {'rejected','conditional'} for d in decisions):raise ValueError('Current rejection or conditional approval prevents release')
    if not any(d['decision']=='approved' and d['approver']!=row['created_by'] for d in decisions):
        raise ValueError('An independent approval of the current evidence revision is required')
