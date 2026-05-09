/**
 * Wire-compatible with the server’s UserResponse. snake_case is preserved
 * because that is what the server emits and the Python SDK exposes.
 */
export interface User {
  id: string;
  email: string;
  created_at: string;
}

/**
 * `expires_in` is populated only on the response from `signUp`,
 * `signInWithPassword`, or `refreshSession`. `getSession()` returns a
 * snapshot with `expires_in: 0` because the real expiry lives in the JWT
 * `exp` claim (parsing it is deferred to a future version).
 */
export interface Session {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: User | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
  user: User;
}

export type AuthChangeEvent = 'SIGNED_IN' | 'SIGNED_OUT' | 'TOKEN_REFRESHED' | 'USER_UPDATED';

export type AuthChangeCallback = (event: AuthChangeEvent, session: Session | null) => void;
