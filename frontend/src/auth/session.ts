const USER_ID_STORAGE_KEY = "arol.user-id";
const ACCESS_TOKEN_STORAGE_KEY = "arol.access-token";

export function activeUserId() { return localStorage.getItem(USER_ID_STORAGE_KEY); }
export function activeAccessToken() { return localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY); }
export function storeSession(userId: string, accessToken: string) {
  localStorage.setItem(USER_ID_STORAGE_KEY, userId);
  localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, accessToken);
}
export function clearSession() {
  localStorage.removeItem(USER_ID_STORAGE_KEY);
  localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY);
}
