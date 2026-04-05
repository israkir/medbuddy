import AsyncStorage from '@react-native-async-storage/async-storage';

import i18n from './index';

export const LANGUAGE_STORAGE_KEY = '@medbuddy/app-language';

export type AppLanguage = 'zh-TW' | 'en';

export async function applyStoredLanguage(): Promise<void> {
  try {
    const saved = await AsyncStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (saved === 'en' || saved === 'zh-TW') {
      await i18n.changeLanguage(saved);
    }
  } catch {
    // ignore corrupt or missing storage
  }
}

export async function setAppLanguage(lng: AppLanguage): Promise<void> {
  await AsyncStorage.setItem(LANGUAGE_STORAGE_KEY, lng);
  await i18n.changeLanguage(lng);
}

export async function clearStoredLanguage(): Promise<void> {
  await AsyncStorage.removeItem(LANGUAGE_STORAGE_KEY);
}
