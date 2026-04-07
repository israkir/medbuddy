import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

import i18next from '@/i18n';
import type { AppLanguage } from '@/i18n/languageStorage';
import {
  apiBaseUrl,
  appUserId,
  mobileBearerToken,
  useMockData,
} from '@/constants/integration';

const ONBOARDING_STORAGE_KEY = 'medbuddy.onboarding_profile.v1';

/** AsyncStorage: recording URI handed off from the tab bar mic to the Medication helper screen. */
export const PENDING_VOICE_HANDOFF_KEY = '@medbuddy/pending_voice_recording_v1';

/** Mirrors backend `ProfileGender` (onboarding / profile patch). */
export type ProfileGender =
  | 'female'
  | 'male'
  | 'non_binary'
  | 'prefer_not_say'
  | 'other';

export type MeProfile = {
  app_user_id: string;
  preferred_name?: string | null;
  age_years?: number | null;
  gender?: ProfileGender | string | null;
  emergency_contact?: string | null;
  health_notes?: string | null;
  /** IANA timezone for reminders (server defaults to Asia/Taipei). */
  timezone?: string | null;
  /** App UI language (`en` or `zh-TW`; server default zh-TW). */
  locale?: AppLanguage | string | null;
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
    gender: null,
    emergency_contact: null,
    health_notes: null,
    timezone: null,
    locale: null,
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
  gender: ProfileGender | null;
  emergency_contact: string;
  health_notes: string;
  /** App UI language; persisted on the user profile. */
  locale: AppLanguage;
  /** IANA timezone; defaults to device zone when omitted. */
  timezone?: string | null;
};

export async function submitOnboarding(payload: OnboardingPayload): Promise<MeProfile> {
  const tz =
    payload.timezone?.trim() ||
    (typeof Intl !== 'undefined'
      ? Intl.DateTimeFormat().resolvedOptions().timeZone
      : null);
  const body = {
    preferred_name: payload.preferred_name.trim(),
    age_years: payload.age_years,
    gender: payload.gender,
    emergency_contact: payload.emergency_contact.trim() || null,
    health_notes: payload.health_notes.trim() || null,
    locale: payload.locale,
    ...(tz ? { timezone: tz } : {}),
  };

  if (useMockData) {
    await Promise.resolve();
    const completed: MeProfile = {
      ...emptyProfile(),
      ...body,
      timezone: tz ?? 'Asia/Taipei',
      locale: payload.locale,
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
    /list (my )?med|what am i taking|my medications|藥品清單|我吃哪些藥|有哪些藥|我的藥/i.test(
      low + userText
    )
  ) {
    return t('companion.mockListMeds');
  }
  if (
    /doctor|visit summary|health summary|看診|給醫師|診間|回診要說/i.test(low + userText) ||
    (/摘要|重點/.test(userText) && /醫|診|藥/.test(userText))
  ) {
    return t('companion.mockDoctorSummary');
  }
  if (
    /family|caregiver|carer|monitor|家人|照顧者|家屬|同步|一起看/i.test(low + userText)
  ) {
    return t('companion.mockFamilyView');
  }
  if (
    /mandarin|chinese voice|中文.*語音|語音.*中文|line.*語音|唸出|朗讀/i.test(low + userText)
  ) {
    return t('companion.mockMandarinVoice');
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

export type CompanionVoiceResult = {
  reply: string;
  transcript: string;
};

/** Upload a local recording (m4a from expo-av); STT + same assistant pipeline as text. */
export async function sendCompanionVoiceMessage(fileUri: string): Promise<CompanionVoiceResult> {
  if (Platform.OS === 'web') {
    throw new Error('Voice messages require the iOS or Android app.');
  }
  if (useMockData) {
    await Promise.resolve();
    const transcript = i18next.language.startsWith('zh') ? '（示範語音）' : '(voice sample)';
    const reply = mockReply(transcript);
    return { reply, transcript };
  }

  const form = new FormData();
  const name = fileUri.split('/').pop()?.split('?')[0] || 'recording.m4a';
  form.append('file', {
    uri: fileUri,
    name,
    type: 'audio/m4a',
  } as unknown as Blob);

  const r = await fetch(`${apiBaseUrl}/v1/app/messages/voice`, {
    method: 'POST',
    headers: mobileHeaders(false),
    body: form,
  });

  if (!r.ok) {
    const body = await r.text();
    throw new Error(body || `${r.status} ${r.statusText}`);
  }

  const data = (await r.json()) as CompanionVoiceResult;
  return {
    reply: data.reply ?? '',
    transcript: data.transcript ?? '',
  };
}
