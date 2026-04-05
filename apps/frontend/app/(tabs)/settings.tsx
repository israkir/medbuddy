import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Link } from 'expo-router';
import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';

import { Text } from '@/components/Themed';
import { fontSize } from '@/constants/accessibility';
import { SCROLL_BOTTOM_INSET } from '@/constants/layout';
import Colors from '@/constants/Colors';
import { type AppLanguage, setAppLanguage } from '@/i18n/languageStorage';
import { useColorScheme } from '@/components/useColorScheme';

const OPTIONS: { lng: AppLanguage; labelKey: 'settings.langZhTW' | 'settings.langEn' }[] = [
  { lng: 'zh-TW', labelKey: 'settings.langZhTW' },
  { lng: 'en', labelKey: 'settings.langEn' },
];

export default function SettingsScreen() {
  const { t, i18n } = useTranslation();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];
  const [busy, setBusy] = useState(false);

  const current = i18n.language.startsWith('zh') ? 'zh-TW' : 'en';

  const onSelect = useCallback(
    async (lng: AppLanguage) => {
      if (lng === current || busy) {
        return;
      }
      setBusy(true);
      try {
        await setAppLanguage(lng);
      } finally {
        setBusy(false);
      }
    },
    [busy, current]
  );

  return (
    <ScrollView
      contentContainerStyle={[
        styles.scroll,
        { paddingBottom: SCROLL_BOTTOM_INSET, backgroundColor: palette.background },
      ]}
      accessibilityLabel={t('tabs.settings')}>
      <Text style={styles.title} maxFontSizeMultiplier={1.6}>
        {t('settings.title')}
      </Text>

      <Link href="/modal" asChild>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t('settings.lineInfoLink')}
          style={({ pressed }) => [
            styles.lineLink,
            { borderColor: palette.tint, opacity: pressed ? 0.85 : 1 },
          ]}>
          <Text style={styles.lineLinkText} maxFontSizeMultiplier={1.5}>
            {t('settings.lineInfoLink')}
          </Text>
          <FontAwesome name="chevron-right" size={18} color={palette.tint} />
        </Pressable>
      </Link>

      <Text style={styles.section} maxFontSizeMultiplier={1.5}>
        {t('settings.language')}
      </Text>
      <Text style={[styles.hint, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.5}>
        {t('settings.hint')}
      </Text>

      {OPTIONS.map(({ lng, labelKey }) => {
        const selected = lng === current;
        return (
          <Pressable
            key={lng}
            accessibilityRole="button"
            accessibilityState={{ selected }}
            accessibilityLabel={t(labelKey)}
            disabled={busy}
            onPress={() => onSelect(lng)}
            style={({ pressed }) => [
              styles.row,
              {
                borderColor: selected ? palette.tint : palette.border,
                backgroundColor: selected ? palette.selectedBackground : 'transparent',
                opacity: pressed ? 0.85 : 1,
              },
            ]}>
            <Text style={styles.rowLabel} maxFontSizeMultiplier={1.5}>
              {t(labelKey)}
            </Text>
            {selected ? (
              <FontAwesome name="check" size={22} color={palette.tint} />
            ) : (
              <View style={styles.checkPlaceholder} />
            )}
          </Pressable>
        );
      })}

      {busy ? <ActivityIndicator style={styles.spinner} color={palette.tint} /> : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    padding: 20,
    paddingBottom: 40,
  },
  title: {
    fontSize: fontSize.title,
    fontWeight: '700',
    marginBottom: 16,
  },
  lineLink: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 16,
    paddingHorizontal: 16,
    borderRadius: 14,
    borderWidth: 2,
    marginBottom: 28,
  },
  lineLinkText: {
    fontSize: fontSize.body,
    fontWeight: '600',
    flex: 1,
    paddingRight: 12,
  },
  section: {
    fontSize: fontSize.body,
    fontWeight: '600',
    marginBottom: 8,
  },
  hint: {
    fontSize: fontSize.caption,
    marginBottom: 20,
    lineHeight: 22,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 16,
    paddingHorizontal: 16,
    borderRadius: 12,
    borderWidth: 2,
    marginBottom: 12,
    minHeight: 52,
  },
  rowLabel: {
    fontSize: fontSize.body,
    flex: 1,
    paddingRight: 12,
  },
  checkPlaceholder: {
    width: 22,
    height: 22,
  },
  spinner: {
    marginTop: 16,
  },
});
