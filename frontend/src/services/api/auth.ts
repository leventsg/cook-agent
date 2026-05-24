/**
 * Authentication API services
 */

import { apiPost } from './client';
import type { Credentials, AuthResponse } from '../../types';

/**
 * User login
 */
export async function login(credentials: Credentials): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/login', credentials);
}

/**
 * User registration
 */
export async function register(credentials: Credentials): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/register', credentials);
}

/**
 * Refresh authentication token
 */
export async function refreshToken(token: string): Promise<AuthResponse> {
  return apiPost<AuthResponse>('/auth/refresh', {}, token);
}
