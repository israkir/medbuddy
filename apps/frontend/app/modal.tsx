import { StatusBar } from 'expo-status-bar';
import { Platform, ScrollView, StyleSheet } from 'react-native';
import { useTranslation } from 'react-i18next';

import { Text, View } from '@/components/Themed';
import { fontSize } from '@/constants/accessibility';
import Colors from '@/constants/Colors';
import { SCROLL_BOTTOM_INSET } from '@/constants/layout';
import { useColorScheme } from '@/components/useColorScheme';

export default function ModalScreen() {
  const { t } = useTranslation();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];

  return (
    <ScrollView
      contentContainerStyle={[styles.scroll, { backgroundColor: palette.background }]}
      style={styles.flex}
      accessibilityLabel={t('modal.title')}>
      <Text style={styles.title} maxFontSizeMultiplier={1.6}>
        {t('modal.title')}
      </Text>
      <Text style={styles.tagline} maxFontSizeMultiplier={1.55}>
        {t('modal.tagline')}
      </Text>
      <View
        style={styles.separator}
        lightColor={Colors.light.separator}
        darkColor={Colors.dark.separator}
      />
      {[t('modal.p1'), t('modal.p2'), t('modal.p3'), t('modal.p4'), t('modal.p5')].map((paragraph, i) => (
        <Text key={i} style={styles.body} maxFontSizeMultiplier={1.55}>
          {paragraph}
        </Text>
      ))}
      <StatusBar style={Platform.OS === 'ios' ? 'light' : 'auto'} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  scroll: {
    padding: 24,
    paddingBottom: SCROLL_BOTTOM_INSET,
  },
  title: {
    fontSize: fontSize.title,
    fontWeight: '700',
    marginBottom: 10,
  },
  tagline: {
    fontSize: fontSize.body,
    fontWeight: '600',
    lineHeight: 30,
    marginBottom: 8,
    opacity: 0.95,
  },
  separator: {
    marginVertical: 18,
    height: 1,
    width: '100%',
  },
  body: {
    fontSize: fontSize.caption,
    lineHeight: 26,
    marginBottom: 16,
    opacity: 0.95,
  },
});
