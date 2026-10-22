import {useEffect,useState} from 'react';
import {api} from './api';

export interface ReleaseNotesPreviewProps{rid:string;open:boolean;onClose:()=>void;}
interface ReleaseNotes{
  release_name:string;
  version:string;
  status:string;
  evidence_revision:number;
  date:string|null;
  summary:string;
  criteria_results:Array<{name:string;status:string;required:boolean;evidence:string}>;
  blockers:Array<{title:string;status:string;resolution:string}>;
  approvals:Array<{approver:string;decision:string;release_revision:number;comment:string}>;
  risk_assessment:{risk_score:number;risk_level:string;ready_for_release:boolean;risk_factors:string[];recommendations:string[];features:Record<string,number>};
  generated_at:string;
}
function StatusBadge({status}:{status:string}){
  const cls=status==='passed'||status==='resolved'||status==='approved'?'ok':status==='failed'||status==='rejected'?'bad':status==='open'?'warn':'';
  return <span className={'badge '+cls}>{status}</span>;
}
function CriteriaTab({criteria}:{criteria:ReleaseNotes['criteria_results']}){
  if(!criteria.length)return <p className="empty">No criteria recorded.</p>;
  return <table className="preview-table"><thead><tr><th>Criterion</th><th>Required</th><th>Status</th><th>Evidence</th></tr></thead><tbody>{criteria.map(c=>(<tr key={c.name}><td>{c.name}</td><td>{c.required?'Yes':'No'}</td><td><StatusBadge status={c.status}/></td><td className="evidence">{c.evidence||'—'}</td></tr>))}</tbody></table>;
}
function BlockersTab({blockers}:{blockers:ReleaseNotes['blockers']}){
  if(!blockers.length)return <p className="empty">No blockers recorded.</p>;
  return <table className="preview-table"><thead><tr><th>Blocker</th><th>Status</th><th>Resolution</th></tr></thead><tbody>{blockers.map(b=>(<tr key={b.title}><td>{b.title}</td><td><StatusBadge status={b.status}/></td><td>{b.resolution||'—'}</td></tr>))}</tbody></table>;
}
function ApprovalsTab({approvals}:{approvals:ReleaseNotes['approvals']}){
  if(!approvals.length)return <p className="empty">No approvals recorded.</p>;
  return <table className="preview-table"><thead><tr><th>Approver</th><th>Decision</th><th>Revision</th><th>Comment</th></tr></thead><tbody>{approvals.map(a=>(<tr key={a.approver+'-'+a.release_revision}><td>{a.approver}</td><td><StatusBadge status={a.decision}/></td><td>{a.release_revision}</td><td>{a.comment||'—'}</td></tr>))}</tbody></table>;
}
function RiskTab({risk}:{risk:ReleaseNotes['risk_assessment']}){
  return(<><div className="metrics"><div><strong>{risk.risk_score}</strong> heuristic risk index / 100</div><div><strong>{risk.risk_level}</strong> heuristic category</div><div><strong>{risk.ready_for_release?'Met':'Not met'}</strong> release evidence gate</div></div><p className="disclaimer">The index uses fixed weights and keyword features. It is not a trained model, a calibrated failure probability, or permission to release. The evidence gate is enforced independently.</p><h4>Risk factors</h4>{risk.risk_factors.length?(<ul>{risk.risk_factors.map(f=><li key={f}>{f}</li>)}</ul>):<p className="empty">None</p>}<h4>Recommendations</h4>{risk.recommendations.length?(<ul>{risk.recommendations.map(r=><li key={r}>{r}</li>)}</ul>):<p className="empty">None</p>}<h4>Scoring features</h4><pre>{JSON.stringify(risk.features,null,2)}</pre></>);
}
export function ReleaseNotesPreview({rid,open,onClose}:ReleaseNotesPreviewProps){
  const [n,setN]=useState<ReleaseNotes|null>(null),[e,setE]=useState(''),[b,setB]=useState(false),[tab,setTab]=useState<'overview'|'criteria'|'blockers'|'approvals'|'risk'>('overview');
  useEffect(()=>{if(open){setB(true);setE('');setTab('overview');api<ReleaseNotes>(`/api/releases/${rid}/release-notes`).then(setN).catch(x=>setE((x as Error).message)).finally(()=>setB(false));}else setN(null);},[open,rid]);
  if(!open)return null;
  return(
    <div className="mo" onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="pt">
      <div className="md" onClick={e=>e.stopPropagation()}>
        <header>
          <h2 id="pt">Release notes preview</h2>
          <button className="cl" onClick={onClose} aria-label="Close preview">×</button>
        </header>
        {b&&<p className="ld">Loading…</p>}
        {e&&<p className="error">{e}</p>}
        {n&&(
          <>
            <div className="header-info">
              <h3>{n.release_name} v{n.version}</h3>
              <div className="mt">
                <span className="badge">{n.status}</span>
                <span>Rev {n.evidence_revision}</span>
                {n.date&&<span>Target: {n.date}</span>}
              </div>
              <p>{n.summary||'No description.'}</p>
            </div>
            <nav className="preview-tabs" role="tablist">
              {(['overview','criteria','blockers','approvals','risk'] as const).map(t=>(<button key={t} role="tab" aria-selected={tab===t} className={tab===t?'active':''} onClick={()=>setTab(t)}>{t.charAt(0).toUpperCase()+t.slice(1)}</button>))}
            </nav>
            <div className="tab-content" role="tabpanel">
              {tab==='overview'&&(
                <>
                  <p>Preview the full release record before exporting. Use tabs to inspect criteria, blockers, approvals, and risk assessment.</p>
                  <p><strong>Generated:</strong> {new Date(n.generated_at).toLocaleString()}</p>
                </>
              )}
              {tab==='criteria'&&<CriteriaTab criteria={n.criteria_results}/>}
              {tab==='blockers'&&<BlockersTab blockers={n.blockers}/>}
              {tab==='approvals'&&<ApprovalsTab approvals={n.approvals}/>}
              {tab==='risk'&&<RiskTab risk={n.risk_assessment}/>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}