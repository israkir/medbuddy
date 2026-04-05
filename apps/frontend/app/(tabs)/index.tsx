import { ScrollView, StyleSheet } from 'react-native';
import { useTranslation } from 'react-i18next';

import { PendingDoseCard } from '@/components/PendingDoseCard';
import { Text, View } from '@/components/Themed';
import { fontSize } from '@/constants/accessibility';
import Colors from '@/constants/Colors';
import { SCROLL_BOTTOM_INSET } from '@/constants/layout';
import { useSharedMedicationExplanations } from '@/context/MedicationExplanationContext';
import { useColorScheme } from '@/components/useColorScheme';

export default function TodayScreen() {
  const { t } = useTranslation();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];
  const { playing, explain, listenBusy } = useSharedMedicationExplanations();

  return (
    <ScrollView
      contentContainerStyle={[
        styles.scroll,
        { backgroundColor: palette.background, paddingBottom: SCROLL_BOTTOM_INSET },
      ]}
      accessibilityLabel={t('tabs.today')}>
      <Text style={[styles.greeting, { color: palette.text }]} maxFontSizeMultiplier={1.6}>
        {t('today.greeting')}
      </Text>

      <View
        style={styles.voicePanel}
        lightColor={Colors.light.voicePanelBg}
        darkColor={Colors.dark.voicePanelBg}>
        <Text style={styles.voiceIntro} maxFontSizeMultiplier={1.6}>
          {t('today.voiceIntro')}
        </Text>
        <Text style={[styles.voiceHint, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.55}>
          {t('voice.sameAsLine')}
        </Text>
      </View>

      <Text style={styles.scheduleTitle} maxFontSizeMultiplier={1.6}>
        {t('today.scheduleTitle')}
      </Text>
      <Text style={[styles.subtitle, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.55}>
        {t('today.subtitle')}
      </Text>

      <PendingDoseCard
        sectionTitle={t('today.sectionMorning')}
        medicationName={t('today.sampleBp')}
        listenLabel={
          playing === 'bp' ? t('medications.explaining') : t('today.listenShort')
        }
        listenDisabled={listenBusy}
        onListen={() => explain('bp')}
        listenA11y={t('a11y.playExplanation')}
        markTakenLabel={t('today.markTaken')}
        markTakenA11y={t('a11y.markDoseTaken')}
        onMarkTaken={() => {}}
      />

      <PendingDoseCard
        sectionTitle={t('today.sectionNoon')}
        medicationName={t('today.sampleMetformin')}
        listenLabel={
          playing === 'metformin' ? t('medications.explaining') : t('today.listenShort')
        }
        listenDisabled={listenBusy}
        onListen={() => explain('metformin')}
        listenA11y={t('a11y.playExplanation')}
        markTakenLabel={t('today.markTaken')}
        markTakenA11y={t('a11y.markDoseTaken')}
        onMarkTaken={() => {}}
      />

      <PendingDoseCard
        sectionTitle={t('today.sectionEvening')}
        medicationName={t('today.sampleStatin')}
        listenLabel={
          playing === 'statin' ? t('medications.explaining') : t('today.listenShort')
        }
        listenDisabled={listenBusy}
        onListen={() => explain('statin')}
        listenA11y={t('a11y.playExplanation')}
        markTakenLabel={t('today.markTaken')}
        markTakenA11y={t('a11y.markDoseTaken')}
        onMarkTaken={() => {}}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    padding: 20,
  },
  greeting: {
    fontSize: fontSize.title,
    fontWeight: '700',
    marginBottom: 16,
    lineHeight: 36,
  },
  voicePanel: {
    borderRadius: 20,
    paddingVertical: 18,
    paddingHorizontal: 16,
    marginBottom: 28,
    width: '100%',
    maxWidth: 520,
    alignSelf: 'center',
  },
  voiceIntro: {
    fontSize: fontSize.caption,
    lineHeight: 28,
    textAlign: 'center',
    marginBottom: 10,
    opacity: 0.96,
  },
  voiceHint: {
    fontSize: fontSize.caption - 1,
    lineHeight: 24,
    textAlign: 'center',
  },
  scheduleTitle: {
    fontSize: fontSize.body,
    fontWeight: '700',
    marginBottom: 6,
  },
  subtitle: {
    fontSize: fontSize.caption,
    marginBottom: 18,
    lineHeight: 26,
  },
});
