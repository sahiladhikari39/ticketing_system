import { isEmbedded, notifyParentUnauthenticated } from "../utils/iframeEmbed";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";
const STORAGE_KEY = "soori_auth";

/**
 * Everything auth-related lives under ONE localStorage key (access,
 * refresh, and user together) rather than three separate keys. They
 * always change together (a login or a refresh updates all of them
 * at once), so keeping them as one JSON blob means there's no way for
 * them to drift out of sync with each other.
 */
export function getStoredAuth() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function setStoredAuth(auth) {
  if (auth === null) {
    localStorage.removeItem(STORAGE_KEY);
  } else {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(auth));
  }
}

/**
 * Logs in against /api/token/ and stores the resulting
 * {access, refresh, user} triple.
 */
export async function login(username, password) {
  const res = await fetch(`${API_BASE_URL}/token/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (!res.ok) {
    throw new Error("Incorrect username or password.");
  }

  const data = await res.json();
  const auth = { access: data.access, refresh: data.refresh, user: data.user };
  setStoredAuth(auth);
  return auth;
}

export function logout() {
  setStoredAuth(null);
}

/**
 * Attempts to exchange the stored refresh token for a new access
 * token. Returns the new access token on success, or null if the
 * refresh token itself is no longer valid (expired, or the user was
 * logged out server-side) -- in which case the caller should treat
 * this as "fully logged out" and send the person back to /login.
 */
async function refreshAccessToken() {
  const auth = getStoredAuth();
  if (!auth?.refresh) return null;

  const res = await fetch(`${API_BASE_URL}/token/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh: auth.refresh }),
  });

  if (!res.ok) {
    setStoredAuth(null);
    return null;
  }

  const data = await res.json();
  // ROTATE_REFRESH_TOKENS is on server-side, so a fresh refresh token
  // often comes back too -- store it if present, otherwise keep the
  // old one.
  const updated = { ...auth, access: data.access, refresh: data.refresh || auth.refresh };
  setStoredAuth(updated);
  return data.access;
}

/**
 * The single function every page uses to talk to the API. Attaches
 * the current access token automatically, and if the server says the
 * token's expired (401), tries exactly ONE silent refresh-and-retry
 * before giving up -- this is what lets a 30-minute access token feel
 * invisible to the person using the app, without ever needing them to
 * log in again mid-session.
 */
export async function apiFetch(path, options = {}) {
  const auth = getStoredAuth();
  const isFormData = options.body instanceof FormData;

  // FormData needs the browser to set its OWN Content-Type header,
  // including the multipart boundary string -- setting
  // "application/json" (or anything else) on a file upload breaks it
  // silently, since the server can no longer find where one field
  // ends and the next begins.
  const headers = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...(options.headers || {}),
  };
  if (auth?.access) {
    headers.Authorization = `Bearer ${auth.access}`;
  }

  let res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (res.status === 401 && auth?.refresh) {
    const newAccess = await refreshAccessToken();
    if (newAccess) {
      res = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers: { ...headers, Authorization: `Bearer ${newAccess}` },
      });
    }
  }

  if (res.status === 401) {
    // Refresh failed too -- the session is genuinely over.
    setStoredAuth(null);
    if (isEmbedded()) {
      // Embedded in someone else's page: redirecting ourselves would
      // render our standalone login screen inside their iframe, which
      // looks like a broken widget. Hand it to the host page instead
      // and let it decide how to present a signed-out state.
      notifyParentUnauthenticated();
    } else {
      window.location.href = "/login";
    }
    throw new Error("Session expired. Please log in again.");
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    let code = null;
    try {
      const body = await res.json();
      code = body.code || null;
      if (body.detail) {
        detail = body.detail;
      } else if (typeof body === "object") {
        // DRF validation errors come back as {field: ["msg", ...]} --
        // flatten that into one readable line instead of raw JSON.
        detail = Object.entries(body)
          .map(([field, messages]) => `${field}: ${Array.isArray(messages) ? messages.join(" ") : messages}`)
          .join(" | ");
      }
    } catch {
      // response wasn't JSON -- keep the generic message
    }
    const err = new Error(detail);
    // Lets a caller check err.code (e.g. "subscription_inactive")
    // instead of pattern-matching on message text, which would break
    // the moment the message wording changes.
    err.code = code;
    throw err;
  }

  if (res.status === 204) return null; // DELETE responses have no body
  return res.json();
}
