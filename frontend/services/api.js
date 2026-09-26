/**
 * Central fetch wrapper — every page talks to the backend only through this file.
 * The Flask backend runs on port 5000 by default.
 */
const API_BASE_URL = "http://127.0.0.1:5000/api";

function getToken() {
  return localStorage.getItem("esd_token");
}

function getCurrentUser() {
  const raw = localStorage.getItem("esd_user");
  return raw ? JSON.parse(raw) : null;
}

function setSession(token, user) {
  localStorage.setItem("esd_token", token);
  localStorage.setItem("esd_user", JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem("esd_token");
  localStorage.removeItem("esd_user");
}

async function apiRequest(path, { method = "GET", body, auth = true, formData = false } = {}) {
  const headers = {};
  if (!formData) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  let res;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? (formData ? body : JSON.stringify(body)) : undefined,
    });
  } catch (err) {
    throw new Error("Could not reach the server. Is the backend running on http://127.0.0.1:5000?");
  }

  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json() : null;

  if (res.status === 401) {
    clearSession();
    if (!location.pathname.endsWith("index.html") && location.pathname !== "/") {
      location.href = "index.html?expired=1";
    }
    throw new Error((data && data.error) || "Session expired.");
  }
  if (!res.ok) {
    throw new Error((data && data.error) || `Request failed (${res.status})`);
  }
  return data;
}

const Api = {
  login: (email, password) => apiRequest("/auth/login", { method: "POST", body: { email, password }, auth: false }),
  logout: () => apiRequest("/auth/logout", { method: "POST" }),
  me: () => apiRequest("/auth/me"),

  listRequests: (params = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v !== undefined && v !== null));
    return apiRequest(`/requests?${qs.toString()}`);
  },
  getRequest: (id) => apiRequest(`/requests/${id}`),
  createRequest: (payload, file) => { const fd = new FormData(); Object.entries(payload).forEach(([k,v]) => { if (v !== null && v !== undefined) fd.append(k, v); }); if (file) fd.append("attachmentFile", file); return apiRequest("/requests", { method: "POST", body: fd, formData: true }); },
  updateRequest: (id, payload) => apiRequest(`/requests/${id}`, { method: "PUT", body: payload }),
  updateStatus: (id, status, note) => apiRequest(`/requests/${id}/status`, { method: "PUT", body: { status, note } }),
  assignRequest: (id, assignedTo) => apiRequest(`/requests/${id}/assign`, { method: "PUT", body: { assignedTo } }),
  reopenRequest: (id, reason) => apiRequest(`/requests/${id}/reopen`, { method: "POST", body: { reason } }),
  addComment: (id, text, internal) => apiRequest(`/requests/${id}/comments`, { method: "POST", body: { text, internal } }),

  employeeDashboard: () => apiRequest("/dashboard/employee"),
  managerDashboard: () => apiRequest("/dashboard/manager"),
  adminDashboard: () => apiRequest("/dashboard/admin"),

  listNotifications: () => apiRequest("/notifications"),
  markNotificationRead: (id) => apiRequest(`/notifications/${id}/read`, { method: "PUT" }),

  departments: () => apiRequest("/meta/departments"),
  categories: () => apiRequest("/meta/categories"),
  users: () => apiRequest("/meta/users"),

  adminUsers: () => apiRequest("/admin/users"),
  adminCreateUser: (payload) => apiRequest("/admin/users", { method: "POST", body: payload }),
  adminUpdateUser: (id, payload) => apiRequest(`/admin/users/${id}`, { method: "PUT", body: payload }),
  adminDepartments: () => apiRequest("/admin/departments"),
  adminCreateDepartment: (payload) => apiRequest("/admin/departments", { method: "POST", body: payload }),
  adminCategories: () => apiRequest("/admin/categories"),
  adminCreateCategory: (payload) => apiRequest("/admin/categories", { method: "POST", body: payload }),
  adminAuditLogs: () => apiRequest("/admin/audit-logs"),
};

window.Api = Api;
window.Session = { getToken, getCurrentUser, setSession, clearSession };
