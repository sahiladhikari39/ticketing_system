import { useEffect, useRef, useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { roleLabel } from "../utils/labels";
import { historyAccessRequestsApi } from "../api/endpoints";

// Some entries gate on a PERMISSION rather than a role. That matters
// for the Knowledge Base especially: a Field Engineer is support_staff,
// but the company's rule is that the video library is never available
// to them -- so showing the link and letting the page come back empty
// would technically comply while reading as a bug.
const NAV_ITEMS = [
  // Sub-Clients are CUSTOMERS, not staff -- their primary action is
  // raising a ticket, so that comes first and their own history is a
  // separate second page. Staff/admins get the shared queue instead.
  { to: "/new-ticket", label: "Raise a ticket", roles: ["sub_client"], primary: true },
  { to: "/tickets", label: "My tickets", roles: ["sub_client"], primary: true },
  { to: "/tickets", label: "Tickets", roles: ["client_admin", "support_staff"], primary: true },
  { to: "/reports", label: "Reports", roles: ["client_admin", "support_staff"], primary: true },
  { to: "/clients", label: "Clients", roles: ["soori_admin"], primary: true },
  { to: "/team", label: "Team", roles: ["client_admin"], primary: true },
  { to: "/knowledge-base", label: "Knowledge Base", permission: "knowledge_base.view", primary: false },
  { to: "/access-codes", label: "Access codes", permission: "service_report.approve", primary: false },
  { to: "/roles", label: "Roles", roles: ["client_admin"], primary: false },
  { to: "/audit-log", label: "Audit log", roles: ["client_admin"], primary: false },
];

/**
 * A dropdown replaces what used to be a horizontally-scrolling row of
 * links -- with several roles' worth of items registered, the row
 * regularly overflowed and needed a scrollbar to reach the rest,
 * which read as unfinished rather than deliberate. One button showing
 * where you are, opening a clean list of everywhere else you can go,
 * scales to any number of items without ever needing to scroll.
 */
function MoreMenu({ items, badgeCount }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    function handleEscape(e) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  if (items.length === 0) return null;

  return (
    <div className="nav-menu" ref={rootRef} style={{ flex: "0 0 auto" }}>
      <button
        type="button"
        className={`nav-menu-trigger${open ? " is-open" : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={open}
        style={{ maxWidth: "none" }}
      >
        <span>More</span>
        {badgeCount > 0 && <span className="nav-badge">{badgeCount}</span>}
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="nav-menu-chevron">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {open && (
        <div className="nav-menu-panel" role="menu">
          {items.map((item) => (
            <NavLink
              key={`${item.to}-${item.label}`}
              to={item.to}
              role="menuitem"
              onClick={() => setOpen(false)}
              className={({ isActive }) => `nav-menu-item${isActive ? " active" : ""}`}
            >
              {item.label}
              {item.to === "/access-codes" && badgeCount > 0 && (
                <span className="nav-badge" style={{ marginLeft: 8 }}>{badgeCount}</span>
              )}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Layout({ children }) {
  const { user, logout } = useAuth();

  const permissions = user.staff_permissions || [];
  const canApprove = permissions.includes("service_report.approve");
  const [pendingCount, setPendingCount] = useState(0);
  const [toast, setToast] = useState(null);
  const knownIds = useRef(new Set());
  const firstCheck = useRef(true);

  useEffect(() => {
    if (!canApprove) return;

    // No real-time push here -- that would need a websocket or
    // long-polling server, which isn't part of this project. Instead
    // this checks periodically and surfaces anything genuinely NEW
    // since the last check as a toast, so a pending request doesn't
    // just sit silently until someone happens to open Access Codes.
    function poll() {
      historyAccessRequestsApi
        .list()
        .then((all) => {
          const pending = all.filter((r) => r.status === "pending");
          setPendingCount(pending.length);

          if (!firstCheck.current) {
            const fresh = pending.filter((r) => !knownIds.current.has(r.id));
            if (fresh.length > 0) {
              const r = fresh[0];
              setToast(
                fresh.length === 1
                  ? `${r.requested_by_username} requested access to ${r.customer_company || r.customer_username}'s history.`
                  : `${fresh.length} new access requests waiting for review.`
              );
              setTimeout(() => setToast(null), 8000);
            }
          }
          firstCheck.current = false;
          knownIds.current = new Set(pending.map((r) => r.id));
        })
        .catch(() => {});
    }

    poll();
    const interval = setInterval(poll, 30000);
    return () => clearInterval(interval);
  }, [canApprove]);

  const visibleItems = NAV_ITEMS.filter((item) =>
    item.permission ? permissions.includes(item.permission) : item.roles.includes(user.role)
  );
  const primaryItems = visibleItems.filter((item) => item.primary);
  const secondaryItems = visibleItems.filter((item) => !item.primary);
  // The badge belongs wherever Access Codes actually is -- inline if
  // this role has few enough items to show it directly, otherwise on
  // the More trigger itself so it's never buried invisibly.
  const accessCodesIsPrimary = primaryItems.some((i) => i.to === "/access-codes");


  return (
    <div className="app-shell">
      {toast && (
        <div
          role="alert"
          style={{
            position: "fixed", top: 16, right: 16, zIndex: 50,
            background: "var(--surface)", border: "1px solid var(--primary)",
            borderRadius: "var(--radius)", boxShadow: "var(--shadow-lg)",
            padding: "14px 18px", maxWidth: 340, display: "flex", gap: 10, alignItems: "flex-start",
          }}
        >
          <span style={{ fontSize: "1.1rem" }}>{"\u{1F514}"}</span>
          <div>
            <div style={{ fontWeight: 600, fontSize: "0.9rem", marginBottom: 2 }}>New access request</div>
            <div style={{ fontSize: "0.85rem", color: "var(--ink-soft)" }}>{toast}</div>
            <Link to="/access-codes" style={{ fontSize: "0.82rem", fontWeight: 600 }} onClick={() => setToast(null)}>
              Review it
            </Link>
          </div>
        </div>
      )}
      <header className="topbar">
        <div className="topbar-inner">
          {/* "/" is a role-aware redirector (see RoleHome in App.jsx),
              so this single link sends every role to their correct
              home without any branching here. */}
          <Link to="/" className="topbar-brand">
            Soori <span>Ticketing System</span>
          </Link>

          <nav className="topbar-primary-nav">
            {primaryItems.map((item) => (
              <NavLink
                key={`${item.to}-${item.label}`}
                to={item.to}
                className={({ isActive }) => `topbar-primary-link${isActive ? " active" : ""}`}
              >
                {item.label}
                {item.to === "/access-codes" && pendingCount > 0 && (
                  <span className="nav-badge" style={{ marginLeft: 6 }}>{pendingCount}</span>
                )}
              </NavLink>
            ))}
          </nav>

          <MoreMenu items={secondaryItems} badgeCount={accessCodesIsPrimary ? 0 : pendingCount} />


          <div className="topbar-user">
            <div className="topbar-user-meta">
              <strong>{user.username}</strong>
              {/* Customers don't need to be told they're customers --
                  the label only means something to staff, who work
                  alongside several roles. */}
              {user.role !== "sub_client" && (
                <span style={{ color: "var(--ink-soft)", fontSize: "0.85rem" }}>
                  {roleLabel(user.role)}
                </span>
              )}
            </div>
            <NavLink
              to="/settings"
              className={({ isActive }) => `topbar-settings${isActive ? " active" : ""}`}
              title="Account settings"
              aria-label="Account settings"
            >
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </NavLink>
            <button className="btn btn-secondary" onClick={logout}>
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="main-content">{children}</main>
    </div>
  );
}
