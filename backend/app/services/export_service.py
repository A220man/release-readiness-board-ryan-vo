"""Release snapshots and portable reports; imported text is inert in exports."""
import csv
import io
import json
from datetime import datetime,timezone
from app.core.risk_engine import risk_engine
from app.services.invariants import current_decisions,require_ready,release_row

class ExportService:
    @staticmethod
    async def _gather_release_data(release_id,db):
        release=await release_row(db,release_id)
        result={'release':release}
        for table in ['criteria','blockers','approvals']:
            rows=await (await db.execute(f'SELECT * FROM {table} WHERE release_id=? ORDER BY created_at,id',(release_id,))).fetchall()
            result[table]=[dict(r) for r in rows]
        for c in result['criteria']:c['required']=bool(c['required'])
        current={a['id'] for a in await current_decisions(db,release_id)}
        for a in result['approvals']:a['is_current']=a['id'] in current
        target=datetime.fromisoformat(release['target_date']) if release.get('target_date') else None
        if target and target.tzinfo is None:target=target.replace(tzinfo=timezone.utc)
        result['days_to_target']=(target-datetime.now(timezone.utc)).days if target else 30
        return result

    @staticmethod
    async def generate_release_notes(release_id,db):
        data=await ExportService._gather_release_data(release_id,db);release=data['release']
        assessment=risk_engine.assess_readiness(dict(data,approvals=[a for a in data['approvals'] if a['is_current']]))
        try:await require_ready(db,release_id);assessment['ready_for_release']=True
        except ValueError as exc:
            assessment['ready_for_release']=False;assessment['risk_factors'].append(str(exc))
        return {'release_name':release['name'],'version':release['version'],'status':release['status'],'evidence_revision':release['revision'],
            'date':release['target_date'],'summary':release['description'],'criteria_results':data['criteria'],
            'blockers_resolved':[b for b in data['blockers'] if b['status']=='resolved'],
            'blockers':data['blockers'],'approvals':data['approvals'],'risk_assessment':assessment,
            'generated_at':datetime.now(timezone.utc).isoformat()}

    @staticmethod
    async def export_json(release_id,db):return json.dumps(await ExportService.generate_release_notes(release_id,db),indent=2)

    @staticmethod
    async def export_markdown(release_id,db):
        notes=await ExportService.generate_release_notes(release_id,db)
        # A variable-length fence prevents imported backticks from ending it.
        text=json.dumps(notes,indent=2,ensure_ascii=False)
        import re
        fence='`'*(max([len(x) for x in re.findall(r'`+',text)]+[2])+1)
        return '# Release readiness evidence\n\nRisk scores are heuristic indices, not failure probabilities.\n\n'+fence+'json\n'+text+'\n'+fence+'\n'

    @staticmethod
    async def export_csv(release_id,db):
        notes=await ExportService.generate_release_notes(release_id,db);out=io.StringIO(newline='');writer=csv.writer(out)
        def cell(v):
            text=str(v)
            return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text
        writer.writerow(['entity','name_or_reviewer','status_or_decision','evidence_revision','detail'])
        for c in notes['criteria_results']:writer.writerow([cell(x) for x in ['criterion',c['name'],c['status'],notes['evidence_revision'],c['evidence']]])
        for b in notes['blockers']:writer.writerow([cell(x) for x in ['blocker',b['title'],b['status'],notes['evidence_revision'],b['resolution']]])
        for a in notes['approvals']:writer.writerow([cell(x) for x in ['approval',a['approver'],a['decision'],a['release_revision'],a['comment']]])
        return out.getvalue()
