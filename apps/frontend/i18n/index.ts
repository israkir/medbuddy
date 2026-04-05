import * as Localization from 'expo-localization';
import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';

import en from '@/locales/en.json';
import zhTW from '@/locales/zh-TW.json';

export const defaultNS = 'translation';

const resources = {
  en: { [defaultNS]: en },
  'zh-TW': { [defaultNS]: zhTW },
} as const;

function resolveInitialLanguage(): string {
  const locales = Localization.getLocales();
  const tag = locales[0]?.languageTag ?? 'zh-TW';
  if (tag.startsWith('zh')) {
    return 'zh-TW';
  }
  if (tag.startsWith('en')) {
    return 'en';
  }
  return 'zh-TW';
}

// Default i18next instance — not the `use` named export from this package.
// eslint-disable-next-line import/no-named-as-default-member -- .use() is i18next's plugin API
void i18next.use(initReactI18next).init({
  resources,
  lng: resolveInitialLanguage(),
  fallbackLng: 'zh-TW',
  defaultNS,
  interpolation: { escapeValue: false },
  compatibilityJSON: 'v4',
});

export default i18next;
