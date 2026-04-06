/**
 * Toggle mock vs real backend data. Set via EXPO_PUBLIC_* in `.env` (see `.env.example`).
 * Defaults to mock so the app runs without an API.
 */
const raw = process.env.EXPO_PUBLIC_USE_MOCK_DATA;

export const useMockData =
  raw === undefined || raw === '' || raw === 'true' || raw === '1';

export const apiBaseUrl =
  process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';

/** Same logical user as backend ``X-App-User-Id`` (alphanumeric + :_.-) */
export const appUserId =
  process.env.EXPO_PUBLIC_APP_USER_ID ?? 'expo-local-user';

/** Optional; required when ``MEDBUDDY_MOBILE_BEARER_TOKEN`` is set on the API. */
export const mobileBearerToken = (process.env.EXPO_PUBLIC_MOBILE_BEARER_TOKEN ?? '').trim();
