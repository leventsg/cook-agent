/**
 * User-related type definitions
 */

export interface Credentials {
  username: string;
  password: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  username: string;
}

export interface UserProfile {
  user_id: string;
  username: string;
  occupation?: string | null;
  bio?: string | null;
  profile?: string | null;
  user_instruction?: string | null;
}

export interface UserProfileUpdateRequest {
  username?: string;
  occupation?: string;
  bio?: string;
  profile?: string;
  user_instruction?: string;
}
