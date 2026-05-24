/**
 * Authentication Context
 * Provides authentication state and methods throughout the app
 */

import { createContext, useContext, useMemo, useState, useCallback } from 'react';
import type { ReactNode } from 'react';
import { loginUser, registerUser, updateProfile as updateUserProfile } from '../services/api';
import { STORAGE_KEYS } from '../constants';
import type { AuthResponse, Credentials, UserProfileUpdateRequest } from '../types';

export interface AuthContextValue {
  token: string | null;
  username: string | null;
  isAuthenticated: boolean;
  login: (credentials: Credentials) => Promise<void>;
  register: (credentials: Credentials) => Promise<void>;
  logout: () => void;
  updateProfile: (data: UserProfileUpdateRequest) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/**
 * Persist auth data to localStorage
 */
function persistAuth(data: AuthResponse): void {
  localStorage.setItem(STORAGE_KEYS.TOKEN, data.access_token);
  localStorage.setItem(STORAGE_KEYS.USERNAME, data.username);
}

/**
 * Clear auth data from localStorage
 */
function clearAuth(): void {
  localStorage.removeItem(STORAGE_KEYS.TOKEN);
  localStorage.removeItem(STORAGE_KEYS.USERNAME);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => 
    localStorage.getItem(STORAGE_KEYS.TOKEN)
  );
  const [username, setUsername] = useState<string | null>(() => 
    localStorage.getItem(STORAGE_KEYS.USERNAME)
  );

  const handleAuthSuccess = useCallback((data: AuthResponse) => {
    setToken(data.access_token);
    setUsername(data.username);
    persistAuth(data);
  }, []);

  const login = useCallback(async (credentials: Credentials) => {
    const res = await loginUser(credentials);
    handleAuthSuccess(res);
  }, [handleAuthSuccess]);

  const register = useCallback(async (credentials: Credentials) => {
    const res = await registerUser(credentials);
    handleAuthSuccess(res);
  }, [handleAuthSuccess]);

  const logout = useCallback(() => {
    setToken(null);
    setUsername(null);
    clearAuth();
  }, []);

  const updateProfile = useCallback(async (data: UserProfileUpdateRequest) => {
    if (!token) throw new Error('Not authenticated');
    const res = await updateUserProfile(data, token);
    if (res.username) {
      setUsername(res.username);
      localStorage.setItem(STORAGE_KEYS.USERNAME, res.username);
    }
  }, [token]);

  const value = useMemo<AuthContextValue>(() => ({
    token,
    username,
    isAuthenticated: Boolean(token),
    login,
    register,
    logout,
    updateProfile,
  }), [token, username, login, register, logout, updateProfile]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * Hook to access authentication context
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
