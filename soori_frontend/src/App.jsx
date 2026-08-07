import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";

/**
 * Every page is loaded lazily -- its JS doesn't download until someone
 * actually navigates there. With 17 pages now, bundling all of them
 * into one file meant a Sub-Client raising a single ticket was
 * downloading the code for Roles, Audit Log, Knowledge Base, and
 * everything else they'll never open. This way the first load only
 * ever pays for the page actually being visited.
 */
const LandingPage = lazy(() => import("./pages/LandingPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const ForgotPasswordPage = lazy(() => import("./pages/ForgotPasswordPage"));
const AccessLoginPage = lazy(() => import("./pages/AccessLoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const TicketDetailPage = lazy(() => import("./pages/TicketDetailPage"));
const NewTicketPage = lazy(() => import("./pages/NewTicketPage"));
const ClientsPage = lazy(() => import("./pages/ClientsPage"));
const ClientDetailPage = lazy(() => import("./pages/ClientDetailPage"));
const TeamPage = lazy(() => import("./pages/TeamPage"));
const AuditLogPage = lazy(() => import("./pages/AuditLogPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const ReportsPage = lazy(() => import("./pages/ReportsPage"));
const KnowledgeBasePage = lazy(() => import("./pages/KnowledgeBasePage"));
const AccessCodesPage = lazy(() => import("./pages/AccessCodesPage"));
const StaffRolesPage = lazy(() => import("./pages/StaffRolesPage"));

/**
 * "/" means something different per role, so it's a pure redirector
 * rather than a page. Keeping this branching in ONE place means no
 * individual page has to carry "...but if you're role X, go
 * elsewhere" logic inside it (DashboardPage used to, awkwardly).
 *
 *   Sub-Client   -> raise a ticket (their main action; history is a
 *                   separate page)
 *   Staff/Admin  -> the shared ticket queue
 *   Soori Admin  -> Clients; they run billing, not a support desk,
 *                   and their ticket queries are empty by design
 */
function RoleHome() {
  const { user } = useAuth();
  if (user.role === "sub_client") return <Navigate to="/new-ticket" replace />;
  if (user.role === "soori_admin") return <Navigate to="/clients" replace />;
  return <Navigate to="/tickets" replace />;
}

/**
 * Shown only for the brief moment a lazily-loaded page's JS is being
 * fetched -- on a normal connection this is barely visible, so it
 * stays plain and quiet rather than a spinner drawing attention to
 * itself for something that fast.
 */
function PageLoadingFallback() {
  return (
    <div style={{ padding: 48, textAlign: "center", color: "var(--ink-soft)", fontSize: "0.9rem" }}>
      Loading...
    </div>
  );
}

function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Suspense fallback={<PageLoadingFallback />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        {/* Reachable while logged OUT -- someone resetting a password
            can't authenticate first. Both steps (request a code, then
            enter it) live on this one page; there's no link to follow,
            so there's nothing to route to in between. */}
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/access-login" element={<AccessLoginPage />} />

        {/* Anonymous visitors see the landing page; logged-in visitors
            get bounced to whichever home matches their role. */}
        <Route path="/" element={isAuthenticated ? <RoleHome /> : <LandingPage />} />

        <Route
          path="/tickets"
          element={
            <ProtectedRoute allowedRoles={["client_admin", "support_staff", "sub_client"]}>
              <DashboardPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/tickets/:id"
          element={
            <ProtectedRoute>
              <TicketDetailPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/new-ticket"
          element={
            <ProtectedRoute allowedRoles={["sub_client"]}>
              <NewTicketPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/clients"
          element={
            <ProtectedRoute allowedRoles={["soori_admin"]}>
              <ClientsPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/clients/:id"
          element={
            <ProtectedRoute allowedRoles={["soori_admin"]}>
              <ClientDetailPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/team"
          element={
            <ProtectedRoute allowedRoles={["client_admin"]}>
              <TeamPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/audit-log"
          element={
            <ProtectedRoute allowedRoles={["client_admin"]}>
              <AuditLogPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/reports"
          element={
            <ProtectedRoute allowedRoles={["client_admin", "support_staff"]}>
              <ReportsPage />
            </ProtectedRoute>
          }
        />

        {/* Gated on PERMISSION, not role -- a Field Engineer is
            support_staff but must never reach the video library, even by
            typing the URL. Enforced server-side too; this just avoids a
            confusing dead end. */}
        <Route
          path="/knowledge-base"
          element={
            <ProtectedRoute requiredPermission="knowledge_base.view">
              <KnowledgeBasePage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/access-codes"
          element={
            <ProtectedRoute requiredPermission="service_report.approve">
              <AccessCodesPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/roles"
          element={
            <ProtectedRoute allowedRoles={["client_admin"]}>
              <StaffRolesPage />
            </ProtectedRoute>
          }
        />

        <Route
          path="/settings"
          element={
            <ProtectedRoute>
              <SettingsPage />
            </ProtectedRoute>
          }
        />
      </Routes>
    </Suspense>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
