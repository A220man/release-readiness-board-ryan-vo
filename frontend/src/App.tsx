import {useEffect, useState} from 'react';
import {api, setCsrf} from './api';
import {User, Release, Criterion, Blocker, Approval, Risk, Audit} from './types';
import {CriteriaPanel} from './CriteriaPanel';
import {BlockersPanel} from './BlockersPanel';
import {ApprovalsPanel} from './ApprovalsPanel';
import {InsightsPanel} from './InsightsPanel';
import {ComparisonPanel} from './ComparisonPanel';

const transitions: Record<string, string[]> = {
  draft: ['in_review', 'cancelled'],
  in_review: ['approved', 'draft', 'cancelled'],
  approved: ['released', 'in_review', 'cancelled'],
  released: [],
  cancelled: ['draft'],
};

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [mode, setMode] = useState('oidc');
  const [loaded, setLoaded] = useState(false);
  const [releases, setReleases] = useState<Release[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Release | null>(null);
  const [criteria, setCriteria] = useState<Criterion[]>([]);
  const [blockers, setBlockers] = useState<Blocker[]>([]);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [risk, setRisk] = useState<Risk | null>(null);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [tab, setTab] = useState('criteria');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState('');
  const [version, setVersion] = useState('1.0.0');
  const [description, setDescription] = useState('');
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showCompare, setShowCompare] = useState(false);

  const operator = !!user?.roles.some(r => ['reviewer', 'admin'].includes(r));
  const admin = !!user?.roles.includes('admin');
  const editable = operator && !!selected && ['draft', 'in_review'].includes(selected.status);

  useEffect(() => {
    let active = true;
    Promise.all([
      api<{mode: string}>('/api/auth/mode'),
      api<User>('/api/auth/me').catch(() => null),
    ]).then(([m, u]) => {
      if (active) {
        setMode(m.mode);
        setUser(u);
        if (u) setCsrf(u.csrf_token);
        setLoaded(true);
      }
    }).catch(e => {
      setError(e.message);
      setLoaded(true);
    });
    return () => { active = false; };
  }, []);

  async function list(p = page, q = query, sf = statusFilter) {
    const params = new URLSearchParams({page: String(p), per_page: '20'});
    if (sf) params.set('status', sf);
    if (q.trim()) params.set('search', q.trim());
    const data = await api<{items: Release[]; total: number}>('/api/releases/?' + params.toString());
    setReleases(data.items);
    setTotal(data.total);
  }

  useEffect(() => {
    if (user) list(page, query, statusFilter).catch(e => setError(e.message));
  }, [user, page, statusFilter]);

  function applySearch() {
    setPage(1);
    list(1, query, statusFilter).catch(e => setError(e.message));
  }

  function resetFilters() {
    setQuery('');
    setStatusFilter('');
    setPage(1);
    list(1, '', '').catch(e => setError(e.message));
  }

  async function login(identity: string) {
    setError('');
    try {
      const u = await api<User>('/api/auth/demo?identity=' + identity, 'POST');
      setCsrf(u.csrf_token);
      setUser(u);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function logout() {
    try {
      await api('/api/auth/logout', 'POST');
      setUser(null);
      setSelected(null);
      setCsrf('');
      setReleases([]);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function open(id: string) {
    setBusy(true);
    setError('');
    try {
      const [r, c, b, a, k, h] = await Promise.all([
        api<Release>('/api/releases/' + id),
        api<Criterion[]>('/api/criteria/release/' + id),
        api<Blocker[]>('/api/blockers/release/' + id),
        api<Approval[]>('/api/approvals/release/' + id),
        api<Risk>('/api/releases/' + id + '/risk-assessment'),
        api<{items: Audit[]}>('/api/audit/release/' + id),
      ]);
      setSelected(r);
      setCriteria(c);
      setBlockers(b);
      setApprovals(a);
      setRisk(k);
      setAudit(h.items);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function refresh() {
    if (selected) void open(selected.id);
    void list().catch(e => setError(e.message));
  }

  async function create() {
    setBusy(true);
    setError('');
    try {
      const r = await api<Release>('/api/releases/', 'POST', {name, version, description});
      setName('');
      setDescription('');
      await list();
      await open(r.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function transition(status: string) {
    if (!selected) return;
    setBusy(true);
    setError('');
    try {
      await api('/api/releases/' + selected.id + '/transition', 'POST', {status});
      await open(selected.id);
      await list();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!selected || !window.confirm('Delete this unreleased release and its evidence? The audit remains.')) return;
    setBusy(true);
    try {
      await api('/api/releases/' + selected.id, 'DELETE');
      setSelected(null);
      await list();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!loaded) return <main><p role="status">Connecting…</p></main>;

  if (!user) {
    return (
      <main className="login">
        <div className="eyebrow">RYAN VO · AI / DEVOPS</div>
        <h1>Release Readiness Board</h1>
        <p>Move from scattered checklists to evidence-backed release decisions, independent approvals and an auditable history.</p>
        <a className="button" href="/api/auth/login">Sign in with SSO</a>
        {mode === 'demo' && (
          <section className="panel">
            <h2>Local demonstration</h2>
            <p>Use analyst to create a release, reviewer for an independent decision, and admin for final approval.</p>
            <div className="actions">
              {['analyst', 'reviewer', 'admin'].map(x => (
                <button key={x} onClick={() => login(x)}>Demo {x}</button>
              ))}
            </div>
          </section>
        )}
        {error && <p role="alert" className="error">{error}</p>}
      </main>
    );
  }

  return (
    <>
      <header>
        <div>
          <div className="eyebrow">RYAN VO · AI / DEVOPS</div>
          <h1>Release Readiness Board</h1>
        </div>
        <div className="identity">
          <span>{user.username} · {user.roles.join(', ')}</span>
          <button className="secondary" onClick={logout}>Sign out</button>
        </div>
      </header>
      <main>
        {error && <p role="alert" className="error">{error}</p>}
        {busy && <p role="status">Loading current release state…</p>}
        {!selected ? (
          <>
            <section className="panel">
              <div className="section-head">
                <h2>Releases ({total})</h2>
                <button className="secondary" onClick={() => list().catch(e => setError(e.message))}>
                  Refresh list
                </button>
              </div>
              <div className="filters">
                <label>
                  Search releases
                  <input
                    placeholder="Search by name or description…"
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') applySearch(); }}
                  />
                </label>
                <label>
                  Status
                  <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }}>
                    <option value="">All statuses</option>
                    <option value="draft">Draft</option>
                    <option value="in_review">In review</option>
                    <option value="approved">Approved</option>
                    <option value="released">Released</option>
                    <option value="cancelled">Cancelled</option>
                  </select>
                </label>
                <button className="secondary" onClick={resetFilters}>Reset</button>
                <button className="button" onClick={applySearch}>Search</button>
              </div>
              <button className="button" onClick={() => setShowCompare(true)} disabled={releases.length < 2}>
                Compare Releases
              </button>
              <table className="release-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Version</th>
                    <th>Status</th>
                    <th>Risk</th>
                    <th>Criteria</th>
                    <th>Blockers</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {releases.map(r => (
                    <tr key={r.id} onClick={() => open(r.id)}>
                      <td>{r.name}</td>
                      <td>{r.version}</td>
                      <td>
                        <span className="badge" style={{
                          backgroundColor: r.status === 'approved' ? '#10b981' :
                            r.status === 'released' ? '#3b82f6' :
                            r.status === 'in_review' ? '#f59e0b' :
                            r.status === 'cancelled' ? '#ef4444' : '#6b7280'
                        }}>
                          {r.status}
                        </span>
                      </td>
                      <td>{r.risk_score?.toFixed(1) ?? '—'}</td>
                      <td>{r.criteria_summary.passed}/{r.criteria_summary.total}</td>
                      <td>{r.blocker_summary.open} open ({r.blocker_summary.critical} critical)</td>
                      <td>{new Date(r.updated_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {total > page * 20 && (
                <button className="secondary" onClick={() => setPage(p => p + 1)}>Load more</button>
              )}
              {releases.length === 0 && <p>No releases match the active filter or search query.</p>}
            </section>
          </>
        ) : (
          <>
            <button className="secondary" onClick={() => { setSelected(null); setShowCompare(false); }}>
              Back to list
            </button>
            <nav aria-label="Release sections">
              {['criteria', 'blockers', 'approvals', 'insights', 'compare'].map(t => (
                <button
                  key={t}
                  className={tab === t ? 'active' : 'secondary'}
                  onClick={() => { setTab(t); setShowCompare(t === 'compare'); }}
                >
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </nav>
            {tab === 'criteria' && <CriteriaPanel rid={selected.id} items={criteria} editable={editable && !busy} refresh={refresh} />}
            {tab === 'blockers' && <BlockersPanel rid={selected.id} items={blockers} editable={editable && !busy} refresh={refresh} />}
            {tab === 'approvals' && <ApprovalsPanel release={selected} items={approvals} user={user} refresh={refresh} />}
            {tab === 'insights' && <InsightsPanel rid={selected.id} risk={risk} audit={audit} editable={operator} />}
            {tab === 'compare' && <ComparisonPanel releases={releases} onClose={() => setTab('criteria')} />}
          </>
        )}
      </main>
      <footer>Ryan Vo · <a href="mailto:ryandtvo@gmail.com">ryandtvo@gmail.com</a> · Human decisions, traceable evidence.</footer>
    </>
  );
}
