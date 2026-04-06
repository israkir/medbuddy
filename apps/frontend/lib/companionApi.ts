import AsyncStorage from '@react-native-async-storage/async-storage';
import i18next from '@/i18n';
import {
  apiBaseUrl,
  appUserId,
  mobileBearerToken,
  useMockData,
} from '@/constants/integration';

const ONBOARDING_STORAGE_KEY = 'medbuddy.onboarding_profile.v1';

export type MeProfile = {
  app_user_id: string;
  preferred_name?: string | null;
  age_years?: number | null;
  emergency_contact?: string | null;
  health_notes?: string | null;
  onboarding_completed_at?: string | null;
};

function mobileHeaders(contentTypeJson: boolean): Record<string, string> {
  const headers: Record<string, string> = {
    'X-App-User-Id': appUserId,
  };
  if (contentTypeJson) {
    headers['Content-Type'] = 'application/json';
  }
  if (mobileBearerToken) {
    headers.Authorization = `Bearer ${mobileBearerToken}`;
  }
  return headers;
}

function emptyProfile(): MeProfile {
  return {
    app_user_id: appUserId,
    preferred_name: null,
    age_years: null,
    emergency_contact: null,
    health_notes: null,
    onboarding_completed_at: null,
  };
}

/** Current user profile + onboarding status (standalone app / same user key as LINE). */
export async function fetchMeProfile(): Promise<MeProfile> {
  if (useMockData) {
    await Promise.resolve();
    const raw = await AsyncStorage.getItem(ONBOARDING_STORAGE_KEY);
    if (!raw) {
      return emptyProfile();
    }
    try {
      const parsed = JSON.parse(raw) as MeProfile;
      return { ...emptyProfile(), ...parsed, app_user_id: appUserId };
    } catch {
      return emptyProfile();
    }
  }

  const r = await fetch(`${apiBaseUrl}/v1/app/me`, {
    headers: mobileHeaders(false),
  });
  if (!r.ok) {
    const body = await r.text();
    throw new Error(body || `${r.status} ${r.statusText}`);
  }
  const data = (await r.json()) as MeProfile;
  return { ...emptyProfile(), ...data };
}

export type OnboardingPayload = {
  preferred_name: string;
  age_years: number | null;
  emergency_contact: string;
  health_notes: string;
};

export async function submitOnboarding(payload: OnboardingPayload): Promise<MeProfile> {
  const body = {
    preferred_name: payload.preferred_name.trim(),
    age_years: payload.age_years,
    emergency_contact: payload.emergency_contact.trim() || null,
    health_notes: payload.health_notes.trim() || null,
  };

  if (useMockData) {
    await Promise.resolve();
    const completed: MeProfile = {
      ...emptyProfile(),
      ...body,
      onboarding_completed_at: new Date().toISOString(),
    };
    await AsyncStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(completed));
    return completed;
  }

  const r = await fetch(`${apiBaseUrl}/v1/app/onboarding`, {
    method: 'POST',
    headers: mobileHeaders(true),
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const errBody = await r.text();
    throw new Error(errBody || `${r.status} ${r.statusText}`);
  }
  const data = (await r.json()) as MeProfile;
  return { ...emptyProfile(), ...data };
}

function mockReply(userText: string): string {
  const t = i18next.t.bind(i18next);
  const low = userText.toLowerCase();
  const isZh = i18next.language.startsWith('zh');
  const together =
    /together|interaction|mix|併用|一起|同時|交互/i.test(userText) ||
    (/一起/.test(userText) && /藥/.test(userText));
  if (together) {
    return t('companion.mockInteraction');
  }
  if (
    /metformin|二甲|雙胍|血糖|aspirin|阿斯匹靈|血壓|statin|膽固醇|cholesterol|bp\b/i.test(
      low + userText
    )
  ) {
    return t('companion.mockDrugDetail');
  }
  if (isZh && (/什麼|做什麼|為什麼|用法|怎麼/.test(userText) || /解釋|說明/.test(userText))) {
    return t('companion.mockDrugDetail');
  }
  if (!isZh && (/what|why|how|explain|purpose/.test(low) || /dose|timing/.test(low))) {
    return t('companion.mockDrugDetail');
  }
  return t('companion.mockGeneric');
}

/**
 * One assistant turn for medication comprehension (backend assistant or offline mock).
 */
export async function sendCompanionMessage(text: string): Promise<string> {
  const trimmed = text.trim();
  if (!trimmed) {
    return '';
  }
  if (useMockData) {
    await Promise.resolve();
    return mockReply(trimmed);
  }

  const r = await fetch(`${apiBaseUrl}/v1/app/messages`, {
    method: 'POST',
    headers: mobileHeaders(true),
    body: JSON.stringify({ text: trimmed }),
  });

  if (!r.ok) {
    const body = await r.text();
    throw new Error(body || `${r.status} ${r.statusText}`);
  }

  const data = (await r.json()) as { reply: string };
  return data.reply ?? '';
}
