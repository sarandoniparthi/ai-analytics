'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

type Role = 'admin' | 'store_manager' | 'marketing' | 'finance';

type Widget = {
  type: string;
  title?: string;
  dataset?: {
    columns?: string[];
    rows?: Array<Array<string | number | boolean | null>>;
    value?: string | number;
    unit?: string;
  };
  config?: { x?: string; y?: string[] };
};

type ApiResponse = {
  answer: string;
  widgets: Widget[];
  sql: { query: string };
  explain: { rag_sources?: string[]; views_used?: string[]; notes?: string };
  security: { role: string; store_id: number; allowed_views: string[]; rls: boolean };
  meta: { exec_ms: number; rows: number; model: string };
};

type Message = {
  id: string;
  question: string;
  response?: ApiResponse;
  error?: string;
};

type AuthUser = {
  user_id: string;
  username: string;
  role: Role;
  store_ids: number[];
  is_all_stores: boolean;
  org_id: string;
};

const ROLE_SCOPE_TEXT: Record<Role, string> = {
  admin: 'payments, rentals, and masked customer data across stores',
  store_manager: 'payments and rentals for your selected store only',
  marketing: 'masked customer data only (no payment or rental details)',
  finance: 'payment data only',
};

const ROLE_ALLOWED_DATASETS: Record<Role, string[]> = {
  admin: ['Payments', 'Rentals', 'Masked Customers'],
  store_manager: ['Payments', 'Rentals'],
  marketing: ['Masked Customers'],
  finance: ['Payments'],
};

const ROLE_PROMPT_EXAMPLES: Record<Role, string[]> = {
  admin: [
    'What is the total revenue for store {store_id}?',
    'Show top 10 customers by total payment amount for store {store_id} as a bar chart.',
    'Show total payment count for store {store_id}.',
    'Show average payment amount for store {store_id}.',
    'Show rental count for store {store_id}.',
    'Show top 10 staff by payment amount for store {store_id} as a bar chart.',
    'Show payment share by store as a pie chart.',
  ],
  store_manager: [
    'What is total revenue for my store {store_id}?',
    'Show top 10 customers by payment amount for my store {store_id} as a bar chart.',
    'Show total payment count for my store {store_id}.',
    'Show average payment amount for my store {store_id}.',
    'Show rental count for my store {store_id}.',
    'Show top 10 staff by payment amount for my store {store_id} as a bar chart.',
    'Show payment count by staff for my store {store_id} as a pie chart.',
  ],
  marketing: [
    'Show total customer count by store as a bar chart.',
    'Show customer counts by store as a bar chart.',
    'Show active customer count by store as a bar chart.',
    'List 20 customers with masked names.',
    'Show customer share by store as a pie chart.',
    'Show customer count split by active status as a pie chart.',
  ],
  finance: [
    'What is total revenue?',
    'Show total payment count.',
    'Show average payment amount.',
    'Show revenue by store as a bar chart.',
    'Show top 10 customers by total payment amount as a bar chart.',
    'Show top 10 staff by payment amount as a bar chart.',
    'Show payment share by staff as a pie chart.',
  ],
};

const PIE_COLORS = ['#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#7c3aed', '#0891b2', '#ea580c', '#9333ea'];

function toChartRows(widget: Widget): Array<Record<string, string | number | null>> {
  const cols = widget.dataset?.columns || [];
  const rows = widget.dataset?.rows || [];
  return rows.map((row) => {
    const entry: Record<string, string | number | null> = {};
    cols.forEach((col, i) => {
      const value = row[i];
      if (typeof value === 'number') {
        entry[col] = Number.isFinite(value) ? value : 0;
      } else if (typeof value === 'string') {
        const parsed = Number(value);
        entry[col] = Number.isFinite(parsed) && value.trim() !== '' ? parsed : value;
      } else if (value == null || typeof value === 'boolean') {
        entry[col] = value == null ? null : String(value);
      } else {
        entry[col] = String(value);
      }
    });
    return entry;
  });
}

function WidgetRenderer({ widget }: { widget: Widget }) {
  if (widget.type === 'metric_card') {
    const value = widget.dataset?.value ?? widget.dataset?.rows?.[0]?.[0] ?? '-';
    return (
      <section className="widget">
        <h4>{widget.title || 'Metric'}</h4>
        <p className="metric-value">
          {String(value)} {widget.dataset?.unit || ''}
        </p>
      </section>
    );
  }

  if (widget.type === 'line') {
    const cols = widget.dataset?.columns || [];
    const rows = toChartRows(widget);
    const xName = widget.config?.x || cols[0] || 'x';
    const yName = widget.config?.y?.[0] || cols[1] || 'y';
    if (cols.length < 2 || !rows.length) return null;
    return (
      <section className="widget">
        <h4>{widget.title || 'Line'}</h4>
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={xName} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey={yName} stroke="#2563eb" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  if (widget.type === 'bar') {
    const cols = widget.dataset?.columns || [];
    const rows = toChartRows(widget);
    const labelCol = cols[0] || 'label';
    const valueCol = cols[1] || 'value';
    if (cols.length < 2 || !rows.length) return null;
    return (
      <section className="widget">
        <h4>{widget.title || 'Bar Chart'}</h4>
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows.slice(0, 20)}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey={labelCol} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey={valueCol} fill="#2563eb" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  if (widget.type === 'pie') {
    const cols = widget.dataset?.columns || [];
    const rows = toChartRows(widget);
    const labelCol = cols[0] || 'label';
    const valueCol = cols[1] || 'value';
    if (cols.length < 2 || !rows.length) return null;
    const pieData = rows
      .map((r) => ({ name: String(r[labelCol] ?? ''), value: Number(r[valueCol] ?? 0) }))
      .filter((r) => Number.isFinite(r.value) && r.value > 0)
      .slice(0, 12);
    if (!pieData.length) return null;
    return (
      <section className="widget">
        <h4>{widget.title || 'Pie Chart'}</h4>
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={90} label>
                {pieData.map((entry, idx) => (
                  <Cell key={entry.name} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </section>
    );
  }

  const cols = widget.dataset?.columns || [];
  const rows = widget.dataset?.rows || [];
  return (
    <section className="widget">
      <h4>{widget.title || 'Table'}</h4>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>{cols.map((col) => <th key={col}>{col}</th>)}</tr>
          </thead>
          <tbody>
            {rows.slice(0, 20).map((row, idx) => (
              <tr key={idx}>
                {row.map((cell, i) => <td key={i}>{String(cell)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function AnalyticsPage() {
  const router = useRouter();
  const [question, setQuestion] = useState('');
  const [storeId, setStoreId] = useState(1);
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [authToken, setAuthToken] = useState('');
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    const token = window.localStorage.getItem('auth_token') || '';
    const userRaw = window.localStorage.getItem('auth_user') || '';
    if (!token || !userRaw) {
      router.replace('/login');
      return;
    }
    try {
      const user = JSON.parse(userRaw) as AuthUser;
      setAuthToken(token);
      setAuthUser(user);
      if (!user.is_all_stores && user.store_ids.length > 0) {
        setStoreId(user.store_ids[0]);
      }
    } catch {
      window.localStorage.removeItem('auth_token');
      window.localStorage.removeItem('auth_user');
      router.replace('/login');
    }
  }, [router]);

  if (!authUser) {
    return null;
  }

  const promptExamples = ROLE_PROMPT_EXAMPLES[authUser.role].map((prompt) =>
    prompt.replaceAll('{store_id}', String(storeId)),
  );

  async function ask() {
    if (!authUser) return;
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    const messageId = crypto.randomUUID();
    setMessages((prev) => [...prev, { id: messageId, question: trimmed }]);
    setQuestion('');
    setLoading(true);

    try {
      const response = await fetch('/api/ask', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          question: trimmed,
          role: authUser.role,
          store_id: storeId,
        }),
      });
      const payload = (await response.json()) as ApiResponse | { detail?: string };
      if (!response.ok) {
        throw new Error((payload as { detail?: string }).detail || 'Request failed');
      }
      setMessages((prev) =>
        prev.map((msg) => (msg.id === messageId ? { ...msg, response: payload as ApiResponse } : msg)),
      );
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Unknown error';
      setMessages((prev) => prev.map((msg) => (msg.id === messageId ? { ...msg, error: detail } : msg)));
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    window.localStorage.removeItem('auth_token');
    window.localStorage.removeItem('auth_user');
    router.replace('/login');
  }

  return (
    <main className="simple-page">
      <header>
        <div className="header-row">
          <div>
            <h1>AI Analytics Copilot</h1>
            <p className="muted">Ask one question, get answer + widgets + SQL + security scope.</p>
          </div>
          <div className="header-actions">
            <span className="user-chip">
              {authUser.username} ({authUser.role})
            </span>
            <button type="button" className="btn-logout" onClick={logout}>
              Logout
            </button>
          </div>
        </div>
      </header>

      <section className="panel controls">
        <div className="scope-banner">
          <strong>Logged in:</strong> {authUser.username} ({authUser.role})
          <div className="scope-datasets">
            {authUser.is_all_stores
              ? 'Store access: all stores'
              : `Store access: ${authUser.store_ids.join(', ') || 'none'}`}
          </div>
          <div className="scope-datasets">Allowed datasets: {ROLE_ALLOWED_DATASETS[authUser.role].join(', ')}</div>
          <div className="scope-datasets">Scope: {ROLE_SCOPE_TEXT[authUser.role]}</div>
        </div>
        <label>
          Store ID
          {authUser.is_all_stores ? (
            <input type="number" value={storeId} onChange={(e) => setStoreId(Number(e.target.value || 0))} />
          ) : (
            <select value={storeId} onChange={(e) => setStoreId(Number(e.target.value || 0))}>
              {authUser.store_ids.map((sid) => (
                <option key={sid} value={sid}>
                  {sid}
                </option>
              ))}
            </select>
          )}
        </label>
      </section>

      <section className="panel ask-box">
        <h3>Ask</h3>
        <div className="prompt-help">
          <p className="muted">Prompt suggestions for your role:</p>
          <div className="prompt-chips">
            {promptExamples.map((example) => (
              <button key={example} type="button" className="guide-chip" onClick={() => setQuestion(example)}>
                {example}
              </button>
            ))}
          </div>
        </div>
        <textarea
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask your analytics question..."
        />
        <button disabled={loading} onClick={() => void ask()}>
          {loading ? 'Running...' : 'Ask'}
        </button>
      </section>

      <section className="results">
        {messages
          .slice()
          .reverse()
          .map((message) => (
            <article key={message.id} className="panel result-card">
              <h3>Question</h3>
              <p>{message.question}</p>
              {message.error ? <p className="error">Error: {message.error}</p> : null}
              {message.response ? (
                <>
                  <h3>Answer</h3>
                  <p>{message.response.answer}</p>
                  <h3>Widgets</h3>
                  <div className="widget-grid">
                    {message.response.widgets.map((widget, idx) => (
                      <WidgetRenderer key={idx} widget={widget} />
                    ))}
                  </div>
                  <h3>Security</h3>
                  <div className="security">
                    <p>role: {message.response.security.role}</p>
                    <p>store_id: {message.response.security.store_id}</p>
                    <p>allowed views: {message.response.security.allowed_views.join(', ')}</p>
                    <p>rls: {String(message.response.security.rls)}</p>
                  </div>
                  <details>
                    <summary>SQL</summary>
                    <pre>{message.response.sql.query}</pre>
                  </details>
                  <details>
                    <summary>Explain</summary>
                    <pre>{JSON.stringify(message.response.explain, null, 2)}</pre>
                  </details>
                  <details>
                    <summary>Meta</summary>
                    <pre>{JSON.stringify(message.response.meta, null, 2)}</pre>
                  </details>
                </>
              ) : null}
            </article>
          ))}
      </section>
    </main>
  );
}
