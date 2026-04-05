import { Platform, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { LargeButton } from '@/components/LargeButton';
import { Text } from '@/components/Themed';
import { fontSize } from '@/constants/accessibility';
import Colors from '@/constants/Colors';
import type { MedicationExplanationId } from '@/hooks/useMedicationExplanations';
import { useColorScheme } from '@/components/useColorScheme';

type Props = {
  medId: MedicationExplanationId;
  remaining: number;
  playing: MedicationExplanationId | null;
  listenBusy: boolean;
  onExplain: (id: MedicationExplanationId) => void;
};

export function MedicationListCard({
  medId,
  remaining,
  playing,
  listenBusy,
  onExplain,
}: Props) {
  const { t } = useTranslation();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];
  const playingThis = playing === medId;
  const key = `medications.items.${medId}` as const;

  const a11y = [
    t(`${key}.name`),
    t('medications.labelDose'),
    t(`${key}.dose`),
    t('medications.labelFrequency'),
    t(`${key}.frequency`),
    t('medications.labelRemaining'),
    t('medications.remainingCount', { count: remaining }),
  ].join('. ');

  return (
    <View
      style={[
        styles.cardOuter,
        {
          backgroundColor: colorScheme === 'dark' ? Colors.dark.cardBackground : Colors.light.cardBackground,
          borderColor: palette.border,
        },
        Platform.select({
          ios: {
            shadowColor: '#0f7669',
            shadowOffset: { width: 0, height: 3 },
            shadowOpacity: 0.12,
            shadowRadius: 8,
          },
          android: { elevation: 3 },
          default: {},
        }),
      ]}
      accessibilityLabel={a11y}>
      <Text style={[styles.medName, { color: palette.text }]} maxFontSizeMultiplier={1.55}>
        {t(`${key}.name`)}
      </Text>

      <View style={styles.fieldsStack}>
        <View
          style={[
            styles.fieldPanel,
            {
              backgroundColor: palette.medicationFieldSurface,
              borderColor: palette.medicationFieldBorder,
            },
          ]}>
          <Text style={[styles.fieldLabel, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.5}>
            {t('medications.labelDose')}
          </Text>
          <Text style={[styles.fieldValue, { color: palette.text }]} maxFontSizeMultiplier={1.5}>
            {t(`${key}.dose`)}
          </Text>
        </View>

        <View
          style={[
            styles.fieldPanel,
            {
              backgroundColor: palette.medicationFieldSurface,
              borderColor: palette.medicationFieldBorder,
            },
          ]}>
          <Text style={[styles.fieldLabel, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.5}>
            {t('medications.labelFrequency')}
          </Text>
          <Text style={[styles.fieldValue, { color: palette.text }]} maxFontSizeMultiplier={1.5}>
            {t(`${key}.frequency`)}
          </Text>
        </View>

        <View
          style={[
            styles.fieldPanel,
            styles.fieldPanelHighlight,
            {
              backgroundColor: palette.medicationFieldSurface,
              borderColor: palette.tint,
            },
          ]}>
          <Text style={[styles.fieldLabel, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.5}>
            {t('medications.labelRemaining')}
          </Text>
          <Text style={[styles.remainingValue, { color: palette.tint }]} maxFontSizeMultiplier={1.5}>
            {t('medications.remainingCount', { count: remaining })}
          </Text>
        </View>
      </View>

      <LargeButton
        label={playingThis ? t('medications.explaining') : t('medications.explain')}
        variant="secondary"
        accessibilityLabel={t('a11y.playExplanation')}
        disabled={listenBusy}
        style={styles.listenButton}
        labelNumberOfLines={2}
        onPress={() => onExplain(medId)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  cardOuter: {
    borderRadius: 18,
    padding: 16,
    marginBottom: 18,
    width: '100%',
    maxWidth: 520,
    alignSelf: 'center',
    borderWidth: 1,
  },
  medName: {
    fontSize: fontSize.title - 2,
    fontWeight: '800',
    marginBottom: 14,
    lineHeight: 34,
    letterSpacing: -0.2,
  },
  fieldsStack: {
    gap: 10,
    marginBottom: 4,
  },
  fieldPanel: {
    borderRadius: 12,
    borderWidth: 1,
    paddingVertical: 12,
    paddingHorizontal: 14,
  },
  fieldPanelHighlight: {
    borderWidth: 2,
  },
  fieldLabel: {
    fontSize: fontSize.caption - 1,
    fontWeight: '700',
    marginBottom: 6,
    lineHeight: 22,
  },
  fieldValue: {
    fontSize: fontSize.body,
    lineHeight: 32,
    fontWeight: '700',
  },
  remainingValue: {
    fontSize: fontSize.body + 2,
    lineHeight: 36,
    fontWeight: '800',
  },
  listenButton: {
    alignSelf: 'stretch',
    marginTop: 16,
    minHeight: 52,
  },
});
