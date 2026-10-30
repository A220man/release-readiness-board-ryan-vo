import {useEffect,useState} from 'react';
import {Release} from './types';
import {api} from './api';

interface ComparisonResult {
  release_a: {
    id: string;
    name: string;
    version: string;
    status: string;
    revision: number;
    risk_score: number;
    criteria_summary: {total: number; passed: number; required_total: number; required_passed: number};
    blocker_summary: {total: number; open: number; critical: number};
  };
  release_b: {
    id: string;
    name: string;
    version: string;
    status: string;
    revision: number;
    risk_score: number;
    criteria_summary: {total: number; passed: number; required_total: number; required_passed: number};
    blocker_summary: {total: number; open: number; critical: number};
  };
  criteria_delta: Array<{
    name: string;
    status_a: string;
    status_b: string;
    required: boolean;
    changed: boolean;
  }>;
  blocker_changes: Array<{
    id: string;
    title_a: string;
    title_b: string;
    severity_a: string;
    severity_b: string;
    status_a: string;
    status_b: string;
    changed: boolean;
  }>;
  approval_diff: {
    release_a: {total: number; approved: number; rejected: number; conditional: number};
    release_b: {total: number; approved: number; rejected: number; conditional: number};
  };
  risk_delta: number;
}

interface TrendPoint {
  id: string;
  name: string;
  version: string;
  status: string;
  risk_score: number;
  updated_at: string;
  total_criteria: number;
  passed_criteria: number;
  open_blockers: number;
  criteria_pass_rate: number;
}

export function ComparisonPanel({releases, onClose}: {releases: Release[]; onClose: () => void}) {
  const [releaseA, setReleaseA] = useState<Release | null>(null);
  const [releaseB, setReleaseB] = useState<Release | null>(null);
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<'compare' | 'trend'>('compare');

  useEffect(() => {
    if (releases.length >= 2) {
      setReleaseA(releases[0]);
      setReleaseB(releases[1]);
      loadTrend();
    }
  }, [releases]);

  async function loadTrend() {
    try {
      const data = await api<TrendPoint[]>('/api/releases/comparison/trend?limit=10');
      setTrend(data);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function doCompare() {
    if (!releaseA || !releaseB || releaseA.id === releaseB.id) return;
    setBusy(true);
    setError('');
    try {
      const data = await api<ComparisonResult>(
        `/api/releases/comparison/compare?a=${releaseA.id}&b=${releaseB.id}`
      );
      setComparison(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function getStatusColor(status: string): string {
    switch (status) {
      case 'draft': return '#6b7280';
      case 'in_review': return '#f59e0b';
      case 'approved': return '#10b981';
      case 'released': return '#3b82f6';
      case 'cancelled': return '#ef4444';
      default: return '#6b7280';
    }
  }

  function getSeverityColor(severity: string): string {
    switch (severity) {
      case 'critical': return '#ef4444';
      case 'high': return '#f97316';
      case 'medium': return '#f59e0b';
      case 'low': return '#10b981';
      default: return '#6b7280';
    }
  }

  function renderComparison() {
    if (!comparison) {
      return (
        <div className="comparison-empty">
          <p>Select two different releases to compare.</p>
          {busy && <p role="status">Comparing…</p>}
        </div>
      );
    }

    const {release_a, release_b, criteria_delta, blocker_changes, approval_diff, risk_delta} = comparison;

    return (
      <div className="comparison-content">
        <div className="comparison-header">
          <div className="release-summary">
            <h3>{release_a.name} v{release_a.version}</h3>
            <span className="status-badge" style={{backgroundColor: getStatusColor(release_a.status)}}>
              {release_a.status}
            </span>
            <p>Revision: {release_a.revision}</p>
            <p>Risk: {release_a.risk_score.toFixed(1)}</p>
            <p>Criteria: {release_a.criteria_summary.passed}/{release_a.criteria_summary.total} passed</p>
            <p>Open Blockers: {release_a.blocker_summary.open} ({release_a.blocker_summary.critical} critical)</p>
          </div>
          <div className="risk-delta">
            <span className={risk_delta > 0 ? 'risk-up' : risk_delta < 0 ? 'risk-down' : 'risk-neutral'}>
              Risk Δ: {risk_delta >= 0 ? '+' : ''}{risk_delta.toFixed(1)}
            </span>
          </div>
          <div className="release-summary">
            <h3>{release_b.name} v{release_b.version}</h3>
            <span className="status-badge" style={{backgroundColor: getStatusColor(release_b.status)}}>
              {release_b.status}
            </span>
            <p>Revision: {release_b.revision}</p>
            <p>Risk: {release_b.risk_score.toFixed(1)}</p>
            <p>Criteria: {release_b.criteria_summary.passed}/{release_b.criteria_summary.total} passed</p>
            <p>Open Blockers: {release_b.blocker_summary.open} ({release_b.blocker_summary.critical} critical)</p>
          </div>
        </div>

        <div className="comparison-tabs">
          <button className={tab === 'compare' ? 'active' : 'secondary'} onClick={() => setTab('compare')}>
            Criteria & Blockers
          </button>
          <button className={tab === 'trend' ? 'active' : 'secondary'} onClick={() => setTab('trend')}>
            Risk Trend
          </button>
        </div>

        {tab === 'compare' && (
          <>
            <section className="comparison-section">
              <h4>Criteria Delta</h4>
              {criteria_delta.length === 0 ? (
                <p>No criteria found in either release.</p>
              ) : (
                <table className="comparison-table">
                  <thead>
                    <tr>
                      <th>Criterion</th>
                      <th>Required</th>
                      <th>{release_a.name}</th>
                      <th>{release_b.name}</th>
                      <th>Changed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {criteria_delta.map((c, i) => (
                      <tr key={i} className={c.changed ? 'changed' : ''}>
                        <td>{c.name}</td>
                        <td>{c.required ? 'Yes' : 'No'}</td>
                        <td>
                          <span className={`status-${c.status_a.toLowerCase().replace('_', '-')}`}>
                            {c.status_a}
                          </span>
                        </td>
                        <td>
                          <span className={`status-${c.status_b.toLowerCase().replace('_', '-')}`}>
                            {c.status_b}
                          </span>
                        </td>
                        <td>{c.changed ? '✓' : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="comparison-section">
              <h4>Blocker Changes</h4>
              {blocker_changes.length === 0 ? (
                <p>No blockers found in either release.</p>
              ) : (
                <table className="comparison-table">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>{release_a.name}</th>
                      <th>{release_b.name}</th>
                      <th>Severity Δ</th>
                      <th>Status Δ</th>
                      <th>Changed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {blocker_changes.map((b, i) => (
                      <tr key={i} className={b.changed ? 'changed' : ''}>
                        <td>{b.id.slice(0, 8)}</td>
                        <td>{b.title_a}</td>
                        <td>{b.title_b}</td>
                        <td>
                          <span style={{color: getSeverityColor(b.severity_a)}}>
                            {b.severity_a}
                          </span>
                          →
                          <span style={{color: getSeverityColor(b.severity_b)}}>
                            {b.severity_b}
                          </span>
                        </td>
                        <td>{b.status_a} → {b.status_b}</td>
                        <td>{b.changed ? '✓' : ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>

            <section className="comparison-section">
              <h4>Approval Summary</h4>
              <table className="comparison-table">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>{release_a.name}</th>
                    <th>{release_b.name}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Total Approvals</td>
                    <td>{approval_diff.release_a.total}</td>
                    <td>{approval_diff.release_b.total}</td>
                  </tr>
                  <tr>
                    <td>Approved</td>
                    <td>{approval_diff.release_a.approved}</td>
                    <td>{approval_diff.release_b.approved}</td>
                  </tr>
                  <tr>
                    <td>Rejected</td>
                    <td>{approval_diff.release_a.rejected}</td>
                    <td>{approval_diff.release_b.rejected}</td>
                  </tr>
                  <tr>
                    <td>Conditional</td>
                    <td>{approval_diff.release_a.conditional}</td>
                    <td>{approval_diff.release_b.conditional}</td>
                  </tr>
                </tbody>
              </table>
            </section>
          </>
        )}

        {tab === 'trend' && (
          <section className="comparison-section">
            <h4>Risk Trend Across Releases</h4>
            {trend.length === 0 ? (
              <p>No trend data available.</p>
            ) : (
              <div className="trend-chart">
                {trend.map((t, i) => (
                  <div key={i} className="trend-point" title={`${t.name} v${t.version} - Risk: ${t.risk_score.toFixed(1)}`}>
                    <div
                      className="trend-bar"
                      style={{
                        height: `${Math.max(2, (t.risk_score / 100) * 150)}px`,
                        backgroundColor:
                          t.risk_score >= 70 ? '#ef4444' :
                          t.risk_score >= 40 ? '#f59e0b' : '#10b981',
                      }}
                    />
                    <span className="trend-label">{t.name} v{t.version}</span>
                    <span className="trend-value">{t.risk_score.toFixed(1)}</span>
                  </div>
                ))}
              </div>
            )}
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Release</th>
                  <th>Status</th>
                  <th>Risk Score</th>
                  <th>Criteria Pass Rate</th>
                  <th>Open Blockers</th>
                </tr>
              </thead>
              <tbody>
                {trend.map((t, i) => (
                  <tr key={i}>
                    <td>{t.name} v{t.version}</td>
                    <td>
                      <span className="status-badge" style={{backgroundColor: getStatusColor(t.status)}}>
                        {t.status}
                      </span>
                    </td>
                    <td>{t.risk_score.toFixed(1)}</td>
                    <td>{(t.criteria_pass_rate * 100).toFixed(1)}%</td>
                    <td>{t.open_blockers}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
      </div>
    );
  }

  return (
    <section className="panel comparison-panel">
      <div className="section-head">
        <h2>Release Comparison</h2>
        <button className="secondary" onClick={onClose}>Close</button>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      <div className="comparison-selectors">
        <label>
          Release A
          <select value={releaseA?.id || ''} onChange={(e) => setReleaseA(releases.find(r => r.id === e.target.value) || null)}>
            <option value="">Select release…</option>
            {releases.map(r => (
              <option key={r.id} value={r.id}>{r.name} v{r.version} ({r.status})</option>
            ))}
          </select>
        </label>
        <label>
          Release B
          <select value={releaseB?.id || ''} onChange={(e) => setReleaseB(releases.find(r => r.id === e.target.value) || null)}>
            <option value="">Select release…</option>
            {releases.map(r => (
              <option key={r.id} value={r.id}>{r.name} v{r.version} ({r.status})</option>
            ))}
          </select>
        </label>
        <button className="button" onClick={doCompare} disabled={busy || !releaseA || !releaseB || releaseA.id === releaseB.id}>
          {busy ? 'Comparing…' : 'Compare'}
        </button>
      </div>
      {renderComparison()}
    </section>
  );
}
