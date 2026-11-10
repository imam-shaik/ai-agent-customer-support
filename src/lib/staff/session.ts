/**
 * Staff session token store — the browser side of staff authentication.
 *
 * The bearer token returned by /auth/login (or /auth/register) is kept
 * in localStorage under a namespaced key so the staff workspace survives
 * reloads. The API client reads it via getToken() to attach the
 * Authorization header; sign-out clears it.
 *
 * Every accessor guards on `typeof window`, so importing this module
 * never breaks server rendering.
 */

const TOKEN_KEY = "vilasat.staff.token";

/** Current staff token, or null when signed out (or on the server). */
export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    // Storage unavailable (private mode / disabled) — treat as signed out.
    return null;
  }
}

/** Persist the token after a successful register/login. */
export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Same as above: the session simply won't survive a reload.
  }
}

/** Forget the token (sign-out or an expired/invalidated session). */
export function clearToken(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Nothing to clean up.
  }
}
