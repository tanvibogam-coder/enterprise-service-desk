/**
 * Shared UI helpers: auth guard, sidebar shell, badges, formatting, notifications.
 * Every page includes this after services/api.js.
 */

function guardPage(allowedRoles) {
  const user = Session.getCurrentUser();
  const token = Session.getToken();
  if (!user || !token) {
    location.href = "index.html";
    return null;
  }
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    location.href = homeForRole(user.role);
    return null;
  }
  return user;
}

function homeForRole(role) {
  if (role === "employee") return "employee-dashboard.html";
  if (role === "executive") return "requests-list.html";
  if (role === "manager") return "manager-dashboard.html";
  if (role === "admin") return "admin.html";
  return "index.html";
}

function initials(name) {
  return (name || "?").split(" ").filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" }) + " " +
    d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function slug(s) {
  return String(s).toLowerCase().replace(/\s+/g, "-");
}

function statusBadge(status) {
  return `<span class="badge badge-status-${slug(status)}"><span class="dot"></span>${status}</span>`;
}
function priorityBadge(priority) {
  return `<span class="badge badge-pri-${slug(priority)}">${priority}</span>`;
}
function slaBadge(sla) {
  const map = {
    SLA_ON_TRACK: ["badge-sla-ok", "On track"],
    SLA_AT_RISK: ["badge-sla-risk", "At risk"],
    SLA_BREACHED: ["badge-sla-breach", "Breached"],
    SLA_BREACHED_ON_CLOSE: ["badge-sla-breach", "Breached (closed)"],
    SLA_MET: ["badge-sla-ok", "Met"],
  };
  const [cls, label] = map[sla] || ["badge-sla-ok", sla];
  return `<span class="badge ${cls}">${label}</span>`;
}

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const NAV_ITEMS = {
  employee: [
    { href: "employee-dashboard.html", label: "Dashboard" },
    { href: "create-request.html", label: "New Request" },
    { href: "requests-list.html", label: "My Requests" },
  ],
  executive: [
    { href: "requests-list.html", label: "Assigned Requests" },
  ],
  manager: [
    { href: "manager-dashboard.html", label: "Manager Dashboard" },
    { href: "requests-list.html", label: "All Requests" },
  ],
  admin: [
    { href: "manager-dashboard.html", label: "Overview" },
    { href: "requests-list.html", label: "All Requests" },
    { href: "admin.html", label: "Admin" },
  ],
};

async function renderShell(activeHref) {
  const user = Session.getCurrentUser();
  if (!user) return;
  const items = NAV_ITEMS[user.role] || [];
  const nav = items
    .map(
      (i) =>
        `<a class="nav-link ${i.href === activeHref ? "active" : ""}" href="${i.href}"><span class="dot"></span>${i.label}</a>`
    )
    .join("");

  document.querySelector(".sidebar").innerHTML = `
    <div class="brand"><span class="mark">SD</span> Service Desk</div>
    <nav>${nav}</nav>
    <div class="spacer"></div>
    <div class="user-card">
      <div class="avatar">${initials(user.name)}</div>
      <div class="user-meta">
        <div class="name">${escapeHtml(user.name)}</div>
        <div class="role">${escapeHtml(user.role)}${user.department ? " · " + escapeHtml(user.department) : ""}</div>
      </div>
    </div>
    <button class="logout-btn" id="logoutBtn">Log out</button>
  `;
  document.getElementById("logoutBtn").addEventListener("click", async () => {
    try { await Api.logout(); } catch (e) { /* ignore */ }
    Session.clearSession();
    location.href = "index.html";
  });

  await initNotifications();
}

async function initNotifications() {
  const bell = document.getElementById("notifBell");
  if (!bell) return;
  let open = false;
  let panel = null;

  async function refreshCount() {
    try {
      const items = await Api.listNotifications();
      const unread = items.filter((n) => !n.read).length;
      const countEl = document.getElementById("notifCount");
      if (unread > 0) {
        countEl.style.display = "flex";
        countEl.textContent = unread > 9 ? "9+" : unread;
      } else {
        countEl.style.display = "none";
      }
      return items;
    } catch (e) {
      return [];
    }
  }

  bell.addEventListener("click", async () => {
    open = !open;
    if (panel) { panel.remove(); panel = null; }
    if (!open) return;
    const items = await Api.listNotifications();
    panel = document.createElement("div");
    panel.className = "notif-panel";
    panel.innerHTML = items.length
      ? items
          .slice(0, 15)
          .map(
            (n) => `<div class="notif-item ${n.read ? "" : "unread"}" data-id="${n.id}" data-req="${n.requestId || ""}">
              <div>${escapeHtml(n.message)}</div>
              <div class="when">${fmtDate(n.createdAt)}</div>
            </div>`
          )
          .join("")
      : `<div class="notif-item">You're all caught up.</div>`;
    document.body.appendChild(panel);
    panel.querySelectorAll(".notif-item[data-id]").forEach((el) => {
      el.addEventListener("click", async () => {
        const id = el.getAttribute("data-id");
        const req = el.getAttribute("data-req");
        try { await Api.markNotificationRead(id); } catch (e) {}
        if (req) location.href = `request-detail.html?id=${req}`;
      });
    });
    document.addEventListener("click", function closeOnce(e) {
      if (panel && !panel.contains(e.target) && e.target !== bell) {
        panel.remove(); panel = null; open = false;
        document.removeEventListener("click", closeOnce);
      }
    });
  });

  await refreshCount();
}

function showAlert(container, message, type = "error") {
  container.innerHTML = `<div class="alert alert-${type}">${escapeHtml(message)}</div>`;
}

function clearAlert(container) {
  container.innerHTML = "";
}
