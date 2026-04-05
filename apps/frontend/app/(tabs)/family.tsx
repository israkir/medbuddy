import { Alert, ScrollView, StyleSheet } from 'react-native';
import { useTranslation } from 'react-i18next';

import { LargeButton } from '@/components/LargeButton';
import { Text } from '@/components/Themed';
import { fontSize } from '@/constants/accessibility';
import { SCROLL_BOTTOM_INSET } from '@/constants/layout';
import Colors from '@/constants/Colors';
import { useColorScheme } from '@/components/useColorScheme';

export default function FamilyScreen() {
  const { t } = useTranslation();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];

  return (
    <ScrollView
      contentContainerStyle={[
        styles.scroll,
        { backgroundColor: palette.background, paddingBottom: SCROLL_BOTTOM_INSET },
      ]}>
      <Text style={styles.title} maxFontSizeMultiplier={1.6}>
        {t('family.title')}
      </Text>
      <Text style={styles.body} maxFontSizeMultiplier={1.6}>
        {t('family.body')}
      </Text>
      <LargeButton
        label={t('family.invite')}
        onPress={() => Alert.alert(t('appName'), t('family.inviteSoon'))}
        style={styles.button}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    padding: 24,
    paddingBottom: 40,
  },
  title: {
    fontSize: fontSize.title,
    fontWeight: '700',
    marginBottom: 16,
  },
  body: {
    fontSize: fontSize.body,
    lineHeight: 32,
    marginBottom: 28,
    opacity: 0.96,
  },
  button: {
    alignSelf: 'stretch',
  },
});
