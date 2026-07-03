// Minimal AuthContext — Phase 1 no-auth mode.
//
// The feihe-specific auth system was removed in Phase 1.
// This stub always reports `isAuthenticated: true` so the app
// skips the login page.  Business auth should be re-implemented
// by each business SKILL's own frontend package.
import { createContext, useContext, type ReactNode } from 'react';

export interface LoginInfo {
  userCode: string;
  companyCode: string;
  displayName?: string | null;
  loggedInAt: string;
}

export interface AuthState {
  isAuthenticated: boolean;
  token: string;
  loginInfo: LoginInfo | null;
  login: (_u: string, _p: string, _c?: string, _cid?: string) => Promise<boolean>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  isAuthenticated: true,
  token: '',
  loginInfo: null,
  login: async () => false,
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const value: AuthState = {
    isAuthenticated: true,
    token: import.meta.env.VITE_MCP_TOKEN ?? '',
    loginInfo: {
      userCode: 'demo',
      companyCode: 'demo',
      displayName: 'Demo User',
      loggedInAt: new Date().toISOString(),
    },
    login: async () => true,
    logout: () => {},
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

export default AuthContext;
