import { useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ScrollView, StyleSheet, View as RNView } from 'react-native';

import { MedicationListCard } from '@/components/MedicationListCard';
import { MedicationQuestionsPanel } from '@/components/MedicationQuestionsPanel';
import { MedicationsQuickJumpBar } from '@/components/MedicationsQuickJumpBar';
import { Text, View } from '@/components/Themed';
import { fontSize } from '@/constants/accessibility';
import { MEDICATION_LIST } from '@/constants/medicationCatalog';
import { SCROLL_BOTTOM_INSET } from '@/constants/layout';
import Colors from '@/constants/Colors';
import { useSharedMedicationExplanations } from '@/context/MedicationExplanationContext';
import { useColorScheme } from '@/components/useColorScheme';

export default function MedicationsScreen() {
  const { t } = useTranslation();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];
  const { playing, explain, listenBusy } = useSharedMedicationExplanations();

  const scrollRef = useRef<ScrollView>(null);
  const listSectionY = useRef(0);
  const questionsSectionY = useRef(0);

  const scrollToList = useCallback(() => {
    scrollRef.current?.scrollTo({
      y: Math.max(0, listSectionY.current - 10),
      animated: true,
    });
  }, []);

  const scrollToQuestions = useCallback(() => {
    scrollRef.current?.scrollTo({
      y: Math.max(0, questionsSectionY.current - 10),
      animated: true,
    });
  }, []);

  return (
    <ScrollView
      ref={scrollRef}
      contentContainerStyle={[
        styles.scroll,
        { backgroundColor: palette.background, paddingBottom: SCROLL_BOTTOM_INSET },
      ]}>
      <View
        style={styles.leadBanner}
        lightColor={Colors.light.voicePanelBg}
        darkColor={Colors.dark.voicePanelBg}>
        <Text style={styles.leadText} maxFontSizeMultiplier={1.55}>
          {t('voice.medicationsLead')}
        </Text>
      </View>

      <Text style={styles.title} maxFontSizeMultiplier={1.6}>
        {t('medications.title')}
      </Text>
      <Text style={[styles.subtitle, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.55}>
        {t('medications.subtitle')}
      </Text>

      <MedicationsQuickJumpBar onJumpList={scrollToList} onJumpQuestions={scrollToQuestions} />

      <RNView
        collapsable={false}
        onLayout={(e) => {
          listSectionY.current = e.nativeEvent.layout.y;
        }}>
        {MEDICATION_LIST.map((row) => (
          <MedicationListCard
            key={row.id}
            medId={row.id}
            remaining={row.remaining}
            playing={playing}
            listenBusy={listenBusy}
            onExplain={explain}
          />
        ))}
      </RNView>

      <RNView
        collapsable={false}
        onLayout={(e) => {
          questionsSectionY.current = e.nativeEvent.layout.y;
        }}>
        <MedicationQuestionsPanel />
      </RNView>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: {
    padding: 20,
    paddingBottom: 40,
  },
  leadBanner: {
    borderRadius: 16,
    padding: 16,
    marginBottom: 22,
  },
  leadText: {
    fontSize: fontSize.caption,
    lineHeight: 26,
    textAlign: 'center',
    fontWeight: '600',
  },
  title: {
    fontSize: fontSize.title,
    fontWeight: '700',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: fontSize.caption,
    marginBottom: 18,
    lineHeight: 26,
  },
});
