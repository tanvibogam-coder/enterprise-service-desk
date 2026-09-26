/**
 * Minimal functional test suite using Node's built-in test runner — no extra
 * dependency needed. Run with: node --test tests/api.test.js
 * Requires the Flask backend to be running on http://127.0.0.1:5000 with the MySQL database
 * initialized using `backend/init_db.py`.
 */
const test = require("node:test");
const assert = require("node:assert");

const BASE = "http://127.0.0.1:5000/api";

async function login(email, password) {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  assert.strictEqual(res.status, 200, `login failed for ${email}: ${JSON.stringify(data)}`);
  return data.token;
}

test("rejects invalid login", async () => {
  const res = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "employee@company.com", password: "wrong" }),
  });
  assert.strictEqual(res.status, 401);
});

test("employee can create a request and see it in their dashboard", async () => {
  const token = await login("employee@company.com", "Employee@123");
  const createRes = await fetch(`${BASE}/requests`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      title: "Automated test request",
      category: "IT Support",
      department: "IT Support",
      description: "Created by the automated test suite.",
      priority: "Low",
    }),
  });
  const created = await createRes.json();
  assert.strictEqual(createRes.status, 201);
  assert.ok(created.request.id.startsWith("REQ-"));

  const dashRes = await fetch(`${BASE}/dashboard/employee`, { headers: { Authorization: `Bearer ${token}` } });
  const dash = await dashRes.json();
  assert.ok(dash.recent.some((r) => r.id === created.request.id));
});

test("employee cannot access admin routes", async () => {
  const token = await login("employee@company.com", "Employee@123");
  const res = await fetch(`${BASE}/admin/users`, { headers: { Authorization: `Bearer ${token}` } });
  assert.strictEqual(res.status, 403);
});

test("executive cannot modify users", async () => {
  const token = await login("executive@company.com", "Executive@123");
  const res = await fetch(`${BASE}/admin/users`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name: "x", email: "x@company.com", role: "employee", password: "x" }),
  });
  assert.strictEqual(res.status, 403);
});

test("closed/resolved requests cannot skip straight back to In Progress via status update", async () => {
  const exec = await login("executive@company.com", "Executive@123");
  const res = await fetch(`${BASE}/requests/REQ-1024/status`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${exec}`, "Content-Type": "application/json" },
    body: JSON.stringify({ status: "In Progress" }),
  });
  // REQ-1024 seeds as "In Progress" already, so move it to Resolved first, then re-check the guard.
  if (res.status === 200) {
    const resolveRes = await fetch(`${BASE}/requests/REQ-1024/status`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${exec}`, "Content-Type": "application/json" },
      body: JSON.stringify({ status: "Resolved" }),
    });
    assert.strictEqual(resolveRes.status, 200);
    const blockedRes = await fetch(`${BASE}/requests/REQ-1024/status`, {
      method: "PUT",
      headers: { Authorization: `Bearer ${exec}`, "Content-Type": "application/json" },
      body: JSON.stringify({ status: "In Progress" }),
    });
    assert.strictEqual(blockedRes.status, 400);
  }
});

test("manager can assign a request to a department executive", async () => {
  const mgr = await login("manager@company.com", "Manager@123");
  const res = await fetch(`${BASE}/requests/REQ-1025/assign`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${mgr}`, "Content-Type": "application/json" },
    body: JSON.stringify({ assignedTo: "U-1005" }),
  });
  const data = await res.json();
  assert.strictEqual(res.status, 200);
  assert.strictEqual(data.assignedTo, "U-1005");
});
