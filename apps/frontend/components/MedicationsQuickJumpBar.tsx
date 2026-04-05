import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { fontSize, MIN_TOUCH } from '@/constants/accessibility';
import Colors from '@/constants/Colors';
import { useColorScheme } from '@/components/useColorScheme';

type Props = {
  onJumpList: () => void;
  onJumpQuestions: () => void;
};

export function MedicationsQuickJumpBar({ onJumpList, onJumpQuestions }: Props) {
  const { t } = useTranslation();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];

  return (
    <View
      style={[
        styles.wrap,
        {
          borderColor: palette.tint,
          backgroundColor: palette.selectedBackground,
        },
      ]}
      accessibilityLabel={t('medications.quickJumpTitle')}>
      <Text style={[styles.heading, { color: palette.text }]} maxFontSizeMultiplier={1.5}>
        {t('medications.quickJumpTitle')}
      </Text>
      <View style={styles.row}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t('medications.quickJumpList')}
          onPress={onJumpList}
          style={({ pressed }) => [
            styles.btn,
            {
              backgroundColor: palette.medicationFieldSurface,
              borderColor: palette.tint,
              opacity: pressed ? 0.88 : 1,
            },
          ]}>
          <FontAwesome name="list-ul" size={22} color={palette.tint} />
          <Text style={[styles.btnLabel, { color: palette.tint }]} maxFontSizeMultiplier={1.45}>
            {t('medications.quickJumpList')}
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={t('medications.quickJumpQuestions')}
          onPress={onJumpQuestions}
          style={({ pressed }) => [
            styles.btn,
            {
              backgroundColor: palette.medicationFieldSurface,
              borderColor: palette.dosePendingAccent,
              opacity: pressed ? 0.88 : 1,
            },
          ]}>
          <FontAwesome name="comment" size={22} color={palette.dosePendingAccent} />
          <Text style={[styles.btnLabel, { color: palette.dosePendingAccent }]} maxFontSizeMultiplier={1.45}>
            {t('medications.quickJumpQuestions')}
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    borderRadius: 16,
    borderWidth: 2,
    padding: 14,
    marginBottom: 20,
    width: '100%',
    maxWidth: 520,
    alignSelf: 'center',
  },
  heading: {
    fontSize: fontSize.caption,
    fontWeight: '800',
    marginBottom: 12,
    letterSpacing: 0.3,
  },
  row: {
    flexDirection: 'row',
    gap: 10,
  },
  btn: {
    flex: 1,
    minHeight: MIN_TOUCH + 6,
    borderRadius: 14,
    borderWidth: 2,
    paddingHorizontal: 10,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  btnLabel: {
    fontSize: fontSize.caption,
    fontWeight: '800',
    textAlign: 'center',
    lineHeight: 22,
  },
});
