import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Layout from "./Layout";

/**
 * Wraps a page that requires login. `allowedRoles` is optional -- when
 * given, a logged-in user whose role isn't in the list gets redirected
 * home rather than seeing the page at all.
 *
 * Important honesty check: this is a UX convenience, not a security
 * boundary. Hiding a nav link or redirecting away from a page doesn't
 * stop someone from calling the API directly -- the ACTUAL security
 * boundary is entirely server-side, in the Django viewsets we already
 * tested. This component exists so the right people see the right
 * screens, not to enforce access control on its own.
 */
export default function ProtectedRoute({ children, allowedRoles, requiredPermission }) {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }

  // Permission-gated routes. Same convenience-not-security caveat as
  // above: the server checks this independently on every request.
  if (requiredPermission && !(user.staff_permissions || []).includes(requiredPermission)) {
    return <Navigate to="/" replace />;
  }

  return <Layout>{children}</Layout>;
}
