import { createContext, useContext, useState, useCallback } from "react";
import { getStoredAuth, login as apiLogin, logout as apiLogout } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => getStoredAuth());

  const login = useCallback(async (username, password) => {
    const result = await apiLogin(username, password);
    setAuth(result);
    return result;
  }, []);

  const logout = useCallback(() => {
    apiLogout();
    setAuth(null);
  }, []);

  const value = {
    user: auth?.user || null,
    isAuthenticated: !!auth?.user,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
