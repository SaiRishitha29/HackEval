import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  UploadCloud,
  Trophy,
  Award,
  Sliders,
  CheckCircle,
  AlertTriangle,
  Clock,
  Lock,
  RefreshCw,
  FileSpreadsheet,
  Terminal,
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface UserInfo {
  username: string;
  email: string;
  role: string;
  team_id?: number;
}

interface TeamInfo {
  id: number;
  name: string;
  contact_email: string;
  submissions_count: number;
  remaining_attempts: number;
}

interface SubmissionItem {
  id: string;
  attempt_number: number;
  excel_filename: string;
  excel_sha256: string;
  endpoint_url: string;
  deployment_version: string;
  status: string;
  is_valid: boolean;
  is_official: boolean;
  submitted_at: string;
  validation_findings: {
    is_valid?: boolean;
    errors?: string[];
    warnings?: string[];
    valid_predictions_count?: number;
    total_rows?: number;
  };
}

interface LeaderboardEntry {
  rank: number;
  team_id: number;
  team_name: string;
  preliminary_accuracy?: number;
  performance_score_p?: number;
  reliability_score_r?: number;
  final_score?: number;
  avg_latency_ms?: number;
  deployment_version?: string;
  is_finalist?: boolean;
}

interface AuditLogItem {
  id: number;
  actor_type: string;
  actor_id: string;
  action: string;
  resource_type: string;
  resource_id?: string;
  details: Record<string, any>;
  timestamp: string;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<'participant' | 'preliminary' | 'final' | 'admin'>('participant');
  const [token, setToken] = useState<string | null>(localStorage.getItem('hackeval_token'));
  const [user, setUser] = useState<UserInfo | null>(null);
  const [team, setTeam] = useState<TeamInfo | null>(null);

  // Participant Form State
  const [file, setFile] = useState<File | null>(null);
  const [endpointUrl, setEndpointUrl] = useState('https://mock-agent.internal/predict');
  const [deploymentVersion, setDeploymentVersion] = useState('v1.0.0');
  const [freezeDeclared, setFreezeDeclared] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [mySubmissions, setMySubmissions] = useState<SubmissionItem[]>([]);

  // Leaderboard States
  const [prelimEntries, setPrelimEntries] = useState<LeaderboardEntry[]>([]);
  const [finalEntries, setFinalEntries] = useState<LeaderboardEntry[]>([]);
  const [isFinalPublished, setIsFinalPublished] = useState(false);
  const [publishedNotes, setPublishedNotes] = useState<string | null>(null);

  // Admin States
  const [adminStats, setAdminStats] = useState<any>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [adminActionLoading, setAdminActionLoading] = useState(false);
  const [adminActionMessage, setAdminActionMessage] = useState<string | null>(null);

  // Login Modal
  const [loginUsername, setLoginUsername] = useState('admin');
  const [loginPassword, setLoginPassword] = useState('HackEvalAdmin2026!');
  const [showLoginModal, setShowLoginModal] = useState(false);

  // Fetch Initial Data
  useEffect(() => {
    fetchLeaderboards();
    fetchCompetitionStatus();
    if (token) {
      fetchCurrentUser(token);
    }
  }, [token]);

  const fetchCompetitionStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/status`);
      if (res.ok) {
        const data = await res.json();
        setAdminStats((prev: any) => ({ ...prev, competition: data }));
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchCurrentUser = async (authToken: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data);
        fetchMyTeam(authToken);
        fetchMySubmissions(authToken);
        if (data.role === 'admin') {
          fetchAdminDashboardData(authToken);
        }
      } else {
        logout();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchMyTeam = async (authToken: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/teams/my-team`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setTeam(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchMySubmissions = async (authToken: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/submissions/my-submissions`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMySubmissions(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchLeaderboards = async () => {
    try {
      const pRes = await fetch(`${API_BASE}/api/leaderboard/preliminary`);
      if (pRes.ok) {
        const pData = await pRes.json();
        setPrelimEntries(pData.entries || []);
      }

      const fRes = await fetch(`${API_BASE}/api/leaderboard/final`);
      if (fRes.ok) {
        const fData = await fRes.json();
        setFinalEntries(fData.entries || []);
        setIsFinalPublished(fData.is_published || false);
        setPublishedNotes(fData.approval_notes || null);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchAdminDashboardData = async (authToken: string) => {
    try {
      const sRes = await fetch(`${API_BASE}/api/admin/competition-status`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (sRes.ok) {
        const data = await sRes.json();
        setAdminStats(data);
      }

      const aRes = await fetch(`${API_BASE}/api/admin/audit-logs?limit=25`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (aRes.ok) {
        const aData = await aRes.json();
        setAuditLogs(aData);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch(`${API_BASE}/api/auth/login-json`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: loginUsername, password: loginPassword }),
      });
      if (res.ok) {
        const data = await res.json();
        setToken(data.access_token);
        localStorage.setItem('hackeval_token', data.access_token);
        setShowLoginModal(false);
      } else {
        alert('Invalid credentials');
      }
    } catch (e) {
      alert('Login error');
    }
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    setTeam(null);
    localStorage.removeItem('hackeval_token');
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) {
      setShowLoginModal(true);
      return;
    }
    if (!file) {
      setSubmitError('Please select a valid .xlsx predictions file.');
      return;
    }
    if (!freezeDeclared) {
      setSubmitError('You must confirm endpoint freeze declaration before submission.');
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('endpoint_url', endpointUrl);
    formData.append('deployment_version', deploymentVersion);
    formData.append('endpoint_freeze_declared', String(freezeDeclared));

    try {
      const res = await fetch(`${API_BASE}/api/submissions/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        setSubmitError(data.detail || 'Submission failed');
      } else {
        setSubmitSuccess(`Attempt #${data.attempt_number} submitted! Status: ${data.status.toUpperCase()}`);
        setFile(null);
        fetchMySubmissions(token);
        fetchMyTeam(token);
      }
    } catch (err: any) {
      setSubmitError(err.message || 'Network error');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Admin Actions
  const handleFreezeDeadline = async () => {
    if (!token) return;
    setAdminActionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/freeze-deadline`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setAdminActionMessage(data.message || 'Deadline frozen and official submissions selected!');
      fetchLeaderboards();
      fetchAdminDashboardData(token);
    } catch (e: any) {
      setAdminActionMessage('Failed to freeze deadline: ' + e.message);
    } finally {
      setAdminActionLoading(false);
    }
  };

  const handleRunVerification = async () => {
    if (!token) return;
    setAdminActionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/verify`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setAdminActionMessage(`Finalist verification initiated for ${data.verified_count} finalists.`);
      fetchLeaderboards();
      fetchAdminDashboardData(token);
    } catch (e: any) {
      setAdminActionMessage('Verification failed: ' + e.message);
    } finally {
      setAdminActionLoading(false);
    }
  };

  const handlePublishFinal = async () => {
    if (!token) return;
    const confirmPub = window.confirm(
      'Are you sure you want to permanently publish the final leaderboard? Published results are strictly immutable.'
    );
    if (!confirmPub) return;

    setAdminActionLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/publish`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ approval_notes: 'Organizer authorized final publication' }),
      });
      const data = await res.json();
      if (res.ok) {
        setAdminActionMessage('Final Leaderboard published and permanently frozen!');
        fetchLeaderboards();
        fetchAdminDashboardData(token);
      } else {
        setAdminActionMessage(data.detail || 'Publication failed');
      }
    } catch (e: any) {
      setAdminActionMessage('Publication error: ' + e.message);
    } finally {
      setAdminActionLoading(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top Header */}
      <header
        style={{
          borderBottom: '1px solid var(--border-subtle)',
          background: 'rgba(11, 15, 25, 0.85)',
          backdropFilter: 'blur(12px)',
          position: 'sticky',
          top: 0,
          zIndex: 40,
        }}
      >
        <div
          style={{
            maxWidth: 1280,
            margin: '0 auto',
            padding: '16px 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div
              style={{
                width: 42,
                height: 42,
                borderRadius: 12,
                background: 'var(--primary-gradient)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: 'var(--shadow-glow)',
              }}
            >
              <ShieldCheck size={26} color="#ffffff" />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <h1 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main)' }}>HackEval</h1>
                <span className="badge badge-verified">Classification Challenge</span>
              </div>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Asia/Kolkata • Max 5 Submissions • Top 20 Finalists • S_final = 0.823529P + 0.176471R
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            {user ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)' }}>
                    {user.username}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {user.role.toUpperCase()} {team ? `• ${team.name}` : ''}
                  </div>
                </div>
                <button onClick={logout} className="btn-secondary" style={{ padding: '6px 12px', fontSize: '0.8rem' }}>
                  Logout
                </button>
              </div>
            ) : (
              <button onClick={() => setShowLoginModal(true)} className="btn-primary">
                Sign In
              </button>
            )}
          </div>
        </div>

        {/* Tab Navigation */}
        <div style={{ maxWidth: 1280, margin: '0 auto', padding: '0 24px', display: 'flex', gap: 8 }}>
          {[
            { id: 'participant', label: 'Participant Portal', icon: UploadCloud },
            { id: 'preliminary', label: 'Provisional Leaderboard', icon: Trophy },
            { id: 'final', label: 'Official Final Leaderboard', icon: Award },
            { id: 'admin', label: 'Admin Control Center', icon: Sliders },
          ].map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '12px 18px',
                  background: 'none',
                  border: 'none',
                  borderBottom: active ? '2px solid var(--primary)' : '2px solid transparent',
                  color: active ? 'var(--text-main)' : 'var(--text-muted)',
                  fontWeight: active ? 600 : 500,
                  fontSize: '0.9rem',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
              >
                <Icon size={18} color={active ? 'var(--primary-light)' : 'currentColor'} />
                {tab.label}
              </button>
            );
          })}
        </div>
      </header>

      {/* Main Content Area */}
      <main style={{ maxWidth: 1280, margin: '0 auto', padding: '32px 24px', flex: 1, width: '100%' }}>
        {/* TAB 1: PARTICIPANT PORTAL */}
        {activeTab === 'participant' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1.8fr)', gap: 28 }}>
            {/* Upload & Submission Form */}
            <div className="glass-panel" style={{ padding: 28 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
                <h2 style={{ fontSize: '1.15rem', fontWeight: 700 }}>Submit Prediction File</h2>
                {team && (
                  <span className="badge badge-provisional">
                    {team.remaining_attempts} of 5 Attempts Remaining
                  </span>
                )}
              </div>

              {submitError && (
                <div
                  style={{
                    background: 'rgba(244, 63, 94, 0.12)',
                    border: '1px solid rgba(244, 63, 94, 0.3)',
                    color: '#f87171',
                    padding: '12px 16px',
                    borderRadius: 10,
                    marginBottom: 18,
                    fontSize: '0.85rem',
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 10,
                  }}
                >
                  <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 2 }} />
                  <div>{submitError}</div>
                </div>
              )}

              {submitSuccess && (
                <div
                  style={{
                    background: 'rgba(16, 185, 129, 0.12)',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    color: '#34d399',
                    padding: '12px 16px',
                    borderRadius: 10,
                    marginBottom: 18,
                    fontSize: '0.85rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                  }}
                >
                  <CheckCircle size={18} />
                  <div>{submitSuccess}</div>
                </div>
              )}

              <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
                {/* Excel File Input */}
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 8, color: 'var(--text-muted)' }}>
                    Excel Predictions Workbook (.xlsx)
                  </label>
                  <div
                    style={{
                      border: '2px dashed var(--border-subtle)',
                      borderRadius: 12,
                      padding: '24px 16px',
                      textAlign: 'center',
                      background: 'rgba(15, 23, 42, 0.4)',
                      cursor: 'pointer',
                      transition: 'border-color 0.2s',
                    }}
                    onClick={() => document.getElementById('excel-file-input')?.click()}
                  >
                    <FileSpreadsheet size={36} color="var(--primary-light)" style={{ margin: '0 auto 8px' }} />
                    <div style={{ fontSize: '0.9rem', fontWeight: 600 }}>
                      {file ? file.name : 'Click or drop .xlsx file here'}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: 4 }}>
                      Columns required: <code style={{ color: 'var(--primary-light)' }}>case_id</code> and <code style={{ color: 'var(--primary-light)' }}>prediction</code>
                    </div>
                    <input
                      id="excel-file-input"
                      type="file"
                      accept=".xlsx"
                      onChange={handleFileChange}
                      style={{ display: 'none' }}
                    />
                  </div>
                </div>

                {/* HTTPS Endpoint URL */}
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6, color: 'var(--text-muted)' }}>
                    Participant Agent HTTPS Endpoint URL
                  </label>
                  <input
                    type="text"
                    value={endpointUrl}
                    onChange={(e) => setEndpointUrl(e.target.value)}
                    placeholder="https://your-agent.hosted-domain.com/predict"
                    className="form-input"
                    required
                  />
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: 4, display: 'block' }}>
                    Finalist endpoint tested independently with fresh hidden test cases.
                  </span>
                </div>

                {/* Deployment Version String */}
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, marginBottom: 6, color: 'var(--text-muted)' }}>
                    Declared Deployment Version
                  </label>
                  <input
                    type="text"
                    value={deploymentVersion}
                    onChange={(e) => setDeploymentVersion(e.target.value)}
                    placeholder="e.g. v1.0.0 or commit hash"
                    className="form-input"
                    required
                  />
                </div>

                {/* Endpoint Freeze Declaration */}
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginTop: 4 }}>
                  <input
                    type="checkbox"
                    id="freeze-check"
                    checked={freezeDeclared}
                    onChange={(e) => setFreezeDeclared(e.target.checked)}
                    style={{ marginTop: 3, accentColor: 'var(--primary)' }}
                  />
                  <label htmlFor="freeze-check" style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                    I declare that this endpoint is deployed and frozen in accordance with the competition policy. I understand the endpoint will be tested without code modifications.
                  </label>
                </div>

                <button type="submit" disabled={isSubmitting} className="btn-primary" style={{ marginTop: 10 }}>
                  {isSubmitting ? (
                    <>
                      <RefreshCw size={18} className="spin" /> Ingesting & Validating...
                    </>
                  ) : (
                    <>
                      <UploadCloud size={18} /> Submit Attempt
                    </>
                  )}
                </button>
              </form>
            </div>

            {/* Submission History */}
            <div className="glass-panel" style={{ padding: 28 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
                <h2 style={{ fontSize: '1.15rem', fontWeight: 700 }}>Submission Attempts History</h2>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  Bound: File + Endpoint + Version
                </span>
              </div>

              {mySubmissions.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '48px 16px', color: 'var(--text-dim)' }}>
                  <Clock size={36} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
                  <p>No submissions recorded yet for your team.</p>
                  <p style={{ fontSize: '0.8rem', marginTop: 4 }}>Submit your first attempt to begin deterministic schema validation.</p>
                </div>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Attempt</th>
                        <th>Filename & SHA-256</th>
                        <th>Endpoint & Version</th>
                        <th>Status</th>
                        <th>Official</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mySubmissions.map((s) => (
                        <tr key={s.id}>
                          <td style={{ fontWeight: 700, color: 'var(--primary-light)' }}>
                            #{s.attempt_number}
                          </td>
                          <td>
                            <div style={{ fontWeight: 600 }}>{s.excel_filename}</div>
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
                              {s.excel_sha256.substring(0, 16)}...
                            </div>
                          </td>
                          <td>
                            <div style={{ fontSize: '0.8rem', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {s.endpoint_url}
                            </div>
                            <span className="badge badge-verified" style={{ fontSize: '0.65rem', padding: '2px 6px' }}>
                              {s.deployment_version}
                            </span>
                          </td>
                          <td>
                            <span className={`badge ${s.is_valid ? 'badge-published' : 'badge-invalid'}`}>
                              {s.status}
                            </span>
                            {s.validation_findings?.errors && s.validation_findings.errors.length > 0 && (
                              <div style={{ fontSize: '0.7rem', color: '#f87171', marginTop: 4 }}>
                                {s.validation_findings.errors[0]}
                              </div>
                            )}
                          </td>
                          <td>
                            {s.is_official ? (
                              <span className="badge badge-published">Official</span>
                            ) : (
                              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: PROVISIONAL PRELIMINARY LEADERBOARD */}
        {activeTab === 'preliminary' && (
          <div className="glass-panel" style={{ padding: 28 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 800 }}>Preliminary Leaderboard</h2>
                  <span className="badge badge-provisional">Provisional — Subject to Official Verification</span>
                </div>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: 4 }}>
                  Calculated against private preliminary ground truth. Top 20 eligible teams qualify as Finalists at freeze deadline.
                </p>
              </div>
              <button onClick={fetchLeaderboards} className="btn-secondary" style={{ fontSize: '0.8rem' }}>
                <RefreshCw size={14} /> Refresh
              </button>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Team Name</th>
                    <th>Preliminary Accuracy</th>
                    <th>Submission ID</th>
                    <th>Timestamp (UTC)</th>
                    <th>Finalist Status</th>
                  </tr>
                </thead>
                <tbody>
                  {prelimEntries.length === 0 ? (
                    <tr>
                      <td colSpan={6} style={{ textAlign: 'center', padding: '36px 0', color: 'var(--text-dim)' }}>
                        Preliminary leaderboard will be generated and frozen at the submission deadline.
                      </td>
                    </tr>
                  ) : (
                    prelimEntries.map((e, idx) => {
                      const isTop20 = idx < 20;
                      return (
                        <tr
                          key={e.team_id}
                          style={{
                            background: isTop20 ? 'rgba(99, 102, 241, 0.05)' : undefined,
                          }}
                        >
                          <td style={{ fontWeight: 800, color: idx === 0 ? '#fbbf24' : 'var(--text-main)' }}>
                            #{idx + 1}
                          </td>
                          <td style={{ fontWeight: 600 }}>{e.team_name}</td>
                          <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--accent-emerald)' }}>
                            {e.preliminary_accuracy !== undefined && e.preliminary_accuracy !== null
                              ? `${(e.preliminary_accuracy * 100).toFixed(2)}%`
                              : 'Hidden before deadline'}
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                            {(e as any).submission_id ? (e as any).submission_id.substring(0, 12) + '...' : '—'}
                          </td>
                          <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                            {(e as any).submission_timestamp ? new Date((e as any).submission_timestamp).toLocaleTimeString() : '—'}
                          </td>
                          <td>
                            {isTop20 ? (
                              <span className="badge badge-published">Top 20 Finalist</span>
                            ) : (
                              <span className="badge badge-provisional">Provisional</span>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 3: OFFICIAL FINAL LEADERBOARD */}
        {activeTab === 'final' && (
          <div className="glass-panel" style={{ padding: 28 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 800 }}>Official Final Leaderboard</h2>
                  {isFinalPublished ? (
                    <span className="badge badge-published">
                      <Lock size={12} /> Published & Immutable
                    </span>
                  ) : (
                    <span className="badge badge-provisional">Provisional Final Preview</span>
                  )}
                </div>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: 4 }}>
                  Numerical scoring formula: <code style={{ color: 'var(--primary-light)' }}>S_final = 0.823529·P + 0.176471·R</code>. Qualitative AI review is disabled.
                </p>
                {publishedNotes && (
                  <p style={{ fontSize: '0.8rem', color: 'var(--accent-cyan)', marginTop: 2 }}>
                    Approval: {publishedNotes}
                  </p>
                )}
              </div>
              <button onClick={fetchLeaderboards} className="btn-secondary" style={{ fontSize: '0.8rem' }}>
                <RefreshCw size={14} /> Refresh
              </button>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Final Rank</th>
                    <th>Team Name</th>
                    <th>Performance P (82.35%)</th>
                    <th>Reliability R (17.65%)</th>
                    <th>Final Score (0–100)</th>
                    <th>Avg Latency</th>
                    <th>Deployment Version</th>
                  </tr>
                </thead>
                <tbody>
                  {finalEntries.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ textAlign: 'center', padding: '36px 0', color: 'var(--text-dim)' }}>
                        Final scores will appear after top-20 finalist endpoint verification is complete.
                      </td>
                    </tr>
                  ) : (
                    finalEntries.map((e, idx) => (
                      <tr
                        key={e.team_id}
                        style={{
                          background: idx === 0 ? 'rgba(251, 191, 36, 0.08)' : undefined,
                        }}
                      >
                        <td style={{ fontWeight: 800, color: idx === 0 ? '#fbbf24' : 'var(--text-main)' }}>
                          {idx === 0 ? '🥇 1' : idx === 1 ? '🥈 2' : idx === 2 ? '🥉 3' : `#${idx + 1}`}
                        </td>
                        <td style={{ fontWeight: 700 }}>{e.team_name}</td>
                        <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-cyan)' }}>
                          {e.performance_score_p?.toFixed(2)}%
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent-emerald)' }}>
                          {e.reliability_score_r?.toFixed(2)}%
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 800, fontSize: '1rem', color: 'var(--text-main)' }}>
                          {e.final_score?.toFixed(4)}
                        </td>
                        <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                          {e.avg_latency_ms ? `${e.avg_latency_ms.toFixed(1)} ms` : 'N/A'}
                        </td>
                        <td>
                          <span className="badge badge-verified" style={{ fontSize: '0.7rem' }}>
                            {e.deployment_version || 'v1.0.0'}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 4: ADMIN CONTROL CENTER */}
        {activeTab === 'admin' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
            {/* Admin Action Controls */}
            <div className="glass-panel" style={{ padding: 28 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
                <div>
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 800 }}>Competition Operations & Controls</h2>
                  <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    Execute frozen evaluation stages with immutable audit trail and MCP synchronization.
                  </p>
                </div>
                {adminStats && (
                  <span className={`badge ${adminStats.is_production_ready ? 'badge-published' : 'badge-provisional'}`}>
                    {adminStats.is_production_ready ? 'Production Ready' : 'Development Mode'}
                  </span>
                )}
              </div>

              {adminActionMessage && (
                <div
                  style={{
                    background: 'rgba(99, 102, 241, 0.12)',
                    border: '1px solid rgba(99, 102, 241, 0.3)',
                    color: '#a5b4fc',
                    padding: '12px 16px',
                    borderRadius: 10,
                    marginBottom: 20,
                    fontSize: '0.85rem',
                  }}
                >
                  {adminActionMessage}
                </div>
              )}

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
                {/* 1. Freeze Deadline */}
                <div
                  style={{
                    background: 'rgba(15, 23, 42, 0.5)',
                    padding: 20,
                    borderRadius: 12,
                    border: '1px solid var(--border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: 6 }}>1. Freeze & Select Official</h3>
                    <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      Freezes submissions and applies deterministic preliminary accuracy selection and tie-breakers.
                    </p>
                  </div>
                  <button
                    onClick={handleFreezeDeadline}
                    disabled={adminActionLoading}
                    className="btn-primary"
                    style={{ marginTop: 14, fontSize: '0.8rem', padding: '8px 14px' }}
                  >
                    Execute Selection
                  </button>
                </div>

                {/* 2. Run Verification */}
                <div
                  style={{
                    background: 'rgba(15, 23, 42, 0.5)',
                    padding: 20,
                    borderRadius: 12,
                    border: '1px solid var(--border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: 6 }}>2. Verify Finalist Endpoints</h3>
                    <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      Launches isolated SSRF-defended workers to test top 20 finalist agents on fresh hidden cases.
                    </p>
                  </div>
                  <button
                    onClick={handleRunVerification}
                    disabled={adminActionLoading}
                    className="btn-primary"
                    style={{ marginTop: 14, fontSize: '0.8rem', padding: '8px 14px' }}
                  >
                    Run Verification
                  </button>
                </div>

                {/* 3. Publish Leaderboard */}
                <div
                  style={{
                    background: 'rgba(15, 23, 42, 0.5)',
                    padding: 20,
                    borderRadius: 12,
                    border: '1px solid var(--border-subtle)',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: 6 }}>3. Approve & Publish Final</h3>
                    <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      Signs off on final scores and creates an immutable published leaderboard snapshot.
                    </p>
                  </div>
                  <button
                    onClick={handlePublishFinal}
                    disabled={adminActionLoading || isFinalPublished}
                    className="btn-primary"
                    style={{ marginTop: 14, fontSize: '0.8rem', padding: '8px 14px', background: isFinalPublished ? '#475569' : undefined }}
                  >
                    {isFinalPublished ? 'Published & Frozen' : 'Approve & Publish'}
                  </button>
                </div>
              </div>
            </div>

            {/* Model Context Protocol (MCP) Integration Info */}
            <div className="glass-panel" style={{ padding: 28 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                <Terminal size={22} color="var(--primary-light)" />
                <h2 style={{ fontSize: '1.15rem', fontWeight: 700 }}>Model Context Protocol (MCP) Server</h2>
              </div>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: 14 }}>
                Evaluation operations are exposed via official Python MCP SDK with administrative token authorization, idempotency, and audit trails.
              </p>
              <div
                style={{
                  background: 'rgba(0, 0, 0, 0.4)',
                  padding: 16,
                  borderRadius: 10,
                  fontFamily: 'var(--font-mono)',
                  fontSize: '0.8rem',
                  color: '#e2e8f0',
                  lineHeight: 1.6,
                }}
              >
                <div><strong>Tools Available:</strong></div>
                <div>• <code style={{ color: 'var(--primary-light)' }}>get_competition_status(admin_token)</code></div>
                <div>• <code style={{ color: 'var(--primary-light)' }}>freeze_and_select_official(admin_token, deadline_override_iso?)</code></div>
                <div>• <code style={{ color: 'var(--primary-light)' }}>get_preliminary_leaderboard(admin_token, limit?)</code></div>
                <div>• <code style={{ color: 'var(--primary-light)' }}>trigger_finalist_verification(admin_token, finalist_ids?)</code></div>
                <div>• <code style={{ color: 'var(--primary-light)' }}>calculate_final_scores(admin_token)</code></div>
                <div>• <code style={{ color: 'var(--primary-light)' }}>publish_final_leaderboard(admin_token, notes)</code></div>
                <div>• <code style={{ color: 'var(--primary-light)' }}>get_audit_trail(admin_token, action?, limit?)</code></div>
              </div>
            </div>

            {/* Immutable Audit Trail */}
            <div className="glass-panel" style={{ padding: 28 }}>
              <h2 style={{ fontSize: '1.15rem', fontWeight: 700, marginBottom: 16 }}>Immutable Platform Audit Trail</h2>
              <div style={{ overflowX: 'auto' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Timestamp (UTC)</th>
                      <th>Actor</th>
                      <th>Action</th>
                      <th>Resource</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {auditLogs.length === 0 ? (
                      <tr>
                        <td colSpan={5} style={{ textAlign: 'center', padding: '24px 0', color: 'var(--text-dim)' }}>
                          No audit records found.
                        </td>
                      </tr>
                    ) : (
                      auditLogs.map((log) => (
                        <tr key={log.id}>
                          <td style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                            {new Date(log.timestamp).toLocaleString()}
                          </td>
                          <td style={{ fontWeight: 600 }}>
                            <span className="badge badge-verified" style={{ fontSize: '0.65rem' }}>
                              {log.actor_type}:{log.actor_id}
                            </span>
                          </td>
                          <td style={{ fontWeight: 700, color: 'var(--primary-light)' }}>{log.action}</td>
                          <td style={{ fontSize: '0.8rem' }}>{log.resource_type}</td>
                          <td style={{ fontSize: '0.75rem', fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>
                            {JSON.stringify(log.details)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Login Modal */}
      {showLoginModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(8px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
          }}
        >
          <div className="glass-panel" style={{ padding: 32, width: '100%', maxWidth: 400 }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: 16 }}>Sign In to HackEval</h2>
            <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Username</label>
                <input
                  type="text"
                  value={loginUsername}
                  onChange={(e) => setLoginUsername(e.target.value)}
                  className="form-input"
                  required
                />
              </div>
              <div>
                <label style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Password</label>
                <input
                  type="password"
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  className="form-input"
                  required
                />
              </div>
              <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
                <button type="submit" className="btn-primary" style={{ flex: 1 }}>
                  Sign In
                </button>
                <button type="button" onClick={() => setShowLoginModal(false)} className="btn-secondary">
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer
        style={{
          borderTop: '1px solid var(--border-subtle)',
          padding: '24px',
          textAlign: 'center',
          color: 'var(--text-dim)',
          fontSize: '0.8rem',
        }}
      >
        HackEval Evaluation Platform • Deterministic Classification Challenge Evaluation • All Rights Reserved
      </footer>
    </div>
  );
}
