import assert from 'node:assert/strict';
import test from 'node:test';

const BASE_URL = process.env.BACKEND_URL || 'http://localhost:3000';

async function postJson(path, body, token) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  return { status: response.status, payload };
}

async function loginUser(username, password) {
  return postJson('/api/auth/login', { username, password });
}

async function ask(question, role, storeId, token) {
  return postJson(
    '/api/ask',
    {
      question,
      role,
      store_id: storeId,
    },
    token,
  );
}

test('login succeeds for seeded manager user', async () => {
  const { status, payload } = await loginUser('manager_store1', 'manager123');

  assert.ok([200, 201].includes(status), `Expected 200/201, got ${status} with payload ${JSON.stringify(payload)}`);
  assert.equal(typeof payload.token, 'string');
  assert.ok(payload.token.length > 20);
  assert.equal(payload.user?.username, 'manager_store1');
  assert.equal(payload.user?.role, 'store_manager');
});

test('login fails with invalid password', async () => {
  const { status } = await loginUser('manager_store1', 'wrong-password');

  assert.equal(status, 401);
});

test('store scope is enforced for manager user', async () => {
  const login = await loginUser('manager_store1', 'manager123');
  assert.ok([200, 201].includes(login.status), `Login precondition failed: ${login.status}`);
  const token = login.payload.token;
  assert.equal(typeof token, 'string');

  const forbidden = await ask('count payments', 'store_manager', 2, token);

  assert.equal(forbidden.status, 403, `Expected 403, got ${forbidden.status}`);
});

test('invalid JWT is rejected', async () => {
  const response = await ask('count payments', 'store_manager', 1, 'not-a-valid-jwt');
  assert.equal(response.status, 401, `Expected 401, got ${response.status}`);
});

test('admin can request any store scope (not blocked by scope guard)', async () => {
  const login = await loginUser('admin_user', 'admin123');
  assert.ok([200, 201].includes(login.status), `Login precondition failed: ${login.status}`);
  const token = login.payload.token;
  assert.equal(typeof token, 'string');

  const response = await ask('count payments', 'admin', 2, token);
  assert.notEqual(response.status, 403, 'Admin should not be forbidden for store 2');
});

test('multi-store manager can request assigned store 2 (not blocked by scope guard)', async () => {
  const login = await loginUser('manager_multi', 'manager123');
  assert.ok([200, 201].includes(login.status), `Login precondition failed: ${login.status}`);
  const token = login.payload.token;
  assert.equal(typeof token, 'string');

  const response = await ask('count payments', 'store_manager', 2, token);
  assert.notEqual(response.status, 403, 'manager_multi should be allowed for store 2');
});

test('finance user is blocked from unassigned store 2', async () => {
  const login = await loginUser('finance_user', 'finance123');
  assert.ok([200, 201].includes(login.status), `Login precondition failed: ${login.status}`);
  const token = login.payload.token;
  assert.equal(typeof token, 'string');

  const forbidden = await ask('count payments', 'finance', 2, token);
  assert.equal(forbidden.status, 403, `Expected 403, got ${forbidden.status}`);
});
