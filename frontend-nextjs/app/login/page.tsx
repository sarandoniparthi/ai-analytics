'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

type Role = 'admin' | 'store_manager' | 'marketing' | 'finance';

type AuthUser = {
  user_id: string;
  username: string;
  role: Role;
  store_ids: number[];
  is_all_stores: boolean;
  org_id: string;
};

type LoginResponse = {
  token: string;
  user: AuthUser;
};

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token = window.localStorage.getItem('auth_token');
    const user = window.localStorage.getItem('auth_user');
    if (token && user) {
      router.replace('/analytics');
    }
  }, [router]);

  async function login() {
    setError('');
    if (!username.trim() || !password.trim()) {
      setError('Username and password are required.');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      const payload = (await response.json()) as LoginResponse | { detail?: string; message?: string };
      if (!response.ok) {
        throw new Error((payload as { detail?: string; message?: string }).detail || 'Login failed');
      }

      const data = payload as LoginResponse;
      window.localStorage.setItem('auth_token', data.token);
      window.localStorage.setItem('auth_user', JSON.stringify(data.user));
      router.replace('/analytics');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <h1>AI Analytics Copilot</h1>
        <p className="muted">Sign in to access role-scoped analytics and widgets.</p>
        <label>
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="manager_store1"
            autoComplete="username"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="manager123"
            autoComplete="current-password"
          />
        </label>
        <button type="button" onClick={() => void login()} disabled={loading}>
          {loading ? 'Signing in...' : 'Sign In'}
        </button>
        {error ? <p className="error">{error}</p> : null}
      </section>
    </main>
  );
}
