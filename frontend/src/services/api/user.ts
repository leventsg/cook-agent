/**
 * User API services
 */

import { apiGet, apiPut } from './client';
import type { UserProfile, UserProfileUpdateRequest } from '../../types';

/**
 * Get current user profile
 */
export async function getProfile(token: string): Promise<UserProfile> {
  return apiGet<UserProfile>('/user/profile', token);
}

/**
 * Update user profile
 */
export async function updateProfile(
  data: UserProfileUpdateRequest,
  token: string
): Promise<UserProfile> {
  return apiPut<UserProfile>('/user/profile', data, token);
}
