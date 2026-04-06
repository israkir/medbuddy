import { Stack, useRouter, type Href } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  TextInput,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Text, View } from '@/components/Themed';
import { fontSize } from '@/constants/accessibility';
import Colors from '@/constants/Colors';
import { useColorScheme } from '@/components/useColorScheme';
import { fetchMeProfile } from '@/lib/companionApi';

const STORAGE_KEY = 'medbuddy.doctor_summary_draft.v1';

type Draft = {
  mainConcern: string;
  symptoms: string;
  medChanges: string;
  questions: string;
  carerNote: string;
  vitals: string;
};

const emptyDraft = (): Draft => ({
  mainConcern: '',
  symptoms: '',
  medChanges: '',
  questions: '',
  carerNote: '',
  vitals: '',
});

export default function DoctorSummaryScreen() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];
  const insets = useSafeAreaInsets();
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [patientName, setPatientName] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await fetchMeProfile();
        if (!cancelled && me.preferred_name) {
          setPatientName(me.preferred_name);
        }
      } catch {
        /* optional */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      if (cancelled) {
        return;
      }
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as Draft;
          setDraft({ ...emptyDraft(), ...parsed });
        } catch {
          setDraft(emptyDraft());
        }
      }
      setLoaded(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const persist = useCallback(async (next: Draft) => {
    setDraft(next);
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }, []);

  const buildDocument = useCallback(() => {
    const locale = i18n.language;
    const dateStr = new Date().toLocaleDateString(
      locale.startsWith('zh') ? 'zh-TW' : undefined,
      { year: 'numeric', month: 'long', day: 'numeric' }
    );
    const lines: string[] = [
      t('doctorSummary.docTitle'),
      `${t('doctorSummary.docDateLabel')} ${dateStr}`,
    ];
    if (patientName?.trim()) {
      lines.push(`${t('doctorSummary.docNameLabel')} ${patientName.trim()}`);
    }
    lines.push('', `— ${t('doctorSummary.sectionMain')} —`, draft.mainConcern.trim() || t('doctorSummary.placeholderEmpty'));
    lines.push('', `— ${t('doctorSummary.sectionSymptoms')} —`, draft.symptoms.trim() || t('doctorSummary.placeholderEmpty'));
    lines.push('', `— ${t('doctorSummary.sectionVitals')} —`, draft.vitals.trim() || t('doctorSummary.placeholderEmpty'));
    lines.push('', `— ${t('doctorSummary.sectionMedChanges')} —`, draft.medChanges.trim() || t('doctorSummary.placeholderEmpty'));
    lines.push('', `— ${t('doctorSummary.sectionQuestions')} —`, draft.questions.trim() || t('doctorSummary.placeholderEmpty'));
    lines.push('', `— ${t('doctorSummary.sectionCarer')} —`, draft.carerNote.trim() || t('doctorSummary.placeholderEmpty'));
    lines.push('', t('doctorSummary.docFooter'));
    return lines.join('\n');
  }, [draft, i18n.language, patientName, t]);

  const onShare = useCallback(async () => {
    const message = buildDocument();
    try {
      await Share.share({ message, title: t('doctorSummary.shareTitle') });
    } catch {
      Alert.alert(t('doctorSummary.shareErrorTitle'), t('doctorSummary.shareErrorBody'));
    }
  }, [buildDocument, t]);

  const onClear = useCallback(() => {
    Alert.alert(t('doctorSummary.clearTitle'), t('doctorSummary.clearBody'), [
      { text: t('doctorSummary.clearCancel'), style: 'cancel' },
      {
        text: t('doctorSummary.clearConfirm'),
        style: 'destructive',
        onPress: () => {
          void persist(emptyDraft());
        },
      },
    ]);
  }, [persist, t]);

  if (!loaded) {
    return null;
  }

  const fieldStyle = [
    styles.field,
    {
      color: palette.text,
      borderColor: palette.dockBorder,
      backgroundColor: palette.medicationFieldSurface,
    },
  ];

  return (
    <>
      <Stack.Screen
        options={{
          title: t('doctorSummary.title'),
          headerBackTitle: t('companion.title'),
        }}
      />
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingBottom: 24 + insets.bottom, backgroundColor: palette.background },
        ]}>
        <Text style={[styles.lead, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.55}>
          {t('doctorSummary.lead')}
        </Text>

        <Text style={[styles.label, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
          {t('doctorSummary.sectionMain')}
        </Text>
        <TextInput
          value={draft.mainConcern}
          onChangeText={(v) => void persist({ ...draft, mainConcern: v })}
          placeholder={t('doctorSummary.phMain')}
          placeholderTextColor={palette.textSecondary}
          multiline
          style={fieldStyle}
          accessibilityLabel={t('doctorSummary.sectionMain')}
        />

        <Text style={[styles.label, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
          {t('doctorSummary.sectionSymptoms')}
        </Text>
        <TextInput
          value={draft.symptoms}
          onChangeText={(v) => void persist({ ...draft, symptoms: v })}
          placeholder={t('doctorSummary.phSymptoms')}
          placeholderTextColor={palette.textSecondary}
          multiline
          style={fieldStyle}
          accessibilityLabel={t('doctorSummary.sectionSymptoms')}
        />

        <Text style={[styles.label, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
          {t('doctorSummary.sectionVitals')}
        </Text>
        <TextInput
          value={draft.vitals}
          onChangeText={(v) => void persist({ ...draft, vitals: v })}
          placeholder={t('doctorSummary.phVitals')}
          placeholderTextColor={palette.textSecondary}
          multiline
          style={fieldStyle}
          accessibilityLabel={t('doctorSummary.sectionVitals')}
        />

        <Text style={[styles.label, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
          {t('doctorSummary.sectionMedChanges')}
        </Text>
        <TextInput
          value={draft.medChanges}
          onChangeText={(v) => void persist({ ...draft, medChanges: v })}
          placeholder={t('doctorSummary.phMedChanges')}
          placeholderTextColor={palette.textSecondary}
          multiline
          style={fieldStyle}
          accessibilityLabel={t('doctorSummary.sectionMedChanges')}
        />

        <Text style={[styles.label, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
          {t('doctorSummary.sectionQuestions')}
        </Text>
        <TextInput
          value={draft.questions}
          onChangeText={(v) => void persist({ ...draft, questions: v })}
          placeholder={t('doctorSummary.phQuestions')}
          placeholderTextColor={palette.textSecondary}
          multiline
          style={fieldStyle}
          accessibilityLabel={t('doctorSummary.sectionQuestions')}
        />

        <Text style={[styles.label, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
          {t('doctorSummary.sectionCarer')}
        </Text>
        <TextInput
          value={draft.carerNote}
          onChangeText={(v) => void persist({ ...draft, carerNote: v })}
          placeholder={t('doctorSummary.phCarer')}
          placeholderTextColor={palette.textSecondary}
          multiline
          style={fieldStyle}
          accessibilityLabel={t('doctorSummary.sectionCarer')}
        />

        <View style={styles.actions} lightColor="transparent" darkColor="transparent">
          <Pressable
            accessibilityRole="button"
            onPress={() => void onShare()}
            style={({ pressed }) => [
              styles.primaryBtn,
              { backgroundColor: palette.tint, opacity: pressed ? 0.88 : 1 },
            ]}>
            <Text style={[styles.primaryBtnText, { color: palette.onPrimary }]} maxFontSizeMultiplier={1.45}>
              {t('doctorSummary.shareCta')}
            </Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={onClear}
            style={({ pressed }) => [
              styles.secondaryBtn,
              {
                borderColor: palette.dockBorder,
                backgroundColor: palette.voicePanelBg,
                opacity: pressed ? 0.88 : 1,
              },
            ]}>
            <Text style={[styles.secondaryBtnText, { color: palette.text }]} maxFontSizeMultiplier={1.45}>
              {t('doctorSummary.clearCta')}
            </Text>
          </Pressable>
        </View>

        <Pressable onPress={() => router.push('/companion' as Href)} style={styles.chatLink}>
          <Text style={{ color: palette.tint, fontWeight: '700' }} maxFontSizeMultiplier={1.45}>
            {t('doctorSummary.backToChat')}
          </Text>
        </Pressable>

        <Text style={[styles.disclaimer, { color: palette.textSecondary }]} maxFontSizeMultiplier={1.45}>
          {t('doctorSummary.disclaimer')}
        </Text>
      </ScrollView>
    </>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingHorizontal: 18,
    paddingTop: 16,
  },
  lead: {
    fontSize: fontSize.caption,
    lineHeight: 24,
    marginBottom: 18,
  },
  label: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 8,
    marginTop: 4,
  },
  field: {
    minHeight: 72,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: fontSize.body,
    lineHeight: 24,
    marginBottom: 14,
    textAlignVertical: 'top',
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginTop: 8,
    marginBottom: 16,
  },
  primaryBtn: {
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 140,
  },
  primaryBtnText: {
    fontSize: 16,
    fontWeight: '700',
  },
  secondaryBtn: {
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    alignItems: 'center',
    justifyContent: 'center',
  },
  secondaryBtnText: {
    fontSize: 16,
    fontWeight: '600',
  },
  chatLink: {
    alignSelf: 'flex-start',
    marginBottom: 20,
  },
  disclaimer: {
    fontSize: 13,
    lineHeight: 22,
    marginBottom: 8,
  },
});
