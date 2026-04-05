/**
 * Toggle mock vs real backend data. Set via EXPO_PUBLIC_* in `.env` (see `.env.example`).
 * Defaults to mock so the app runs without an API.
 */
const raw = process.env.EXPO_PUBLIC_USE_MOCK_DATA;

export const useMockData =
  raw === undefined || raw === '' || raw === 'true' || raw === '1';

export const apiBaseUrl =
  process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000';
