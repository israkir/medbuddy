import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { LargeButton } from '@/components/LargeButton';
import { Text as ThemedText } from '@/components/Themed';
import { fontSize, MIN_TOUCH } from '@/constants/accessibility';
import Colors from '@/constants/Colors';
import { useColorScheme } from '@/components/useColorScheme';

type Props = {
  sectionTitle: string;
  medicationName: string;
  onListen: () => void;
  listenLabel: string;
  listenDisabled: boolean;
  onMarkTaken: () => void;
  markTakenLabel: string;
  markTakenA11y: string;
  listenA11y?: string;
};

export function PendingDoseCard({
  sectionTitle,
  medicationName,
  onListen,
  listenLabel,
  listenDisabled,
  onMarkTaken,
  markTakenLabel,
  markTakenA11y,
  listenA11y,
}: Props) {
  const { t } = useTranslation();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: palette.dosePendingSurface,
          borderLeftColor: palette.dosePendingAccent,
        },
      ]}
      accessibilityLabel={`${sectionTitle}. ${medicationName}. ${t('today.notTakenYet')}`}>
      <View style={styles.topRow}>
        <View style={styles.badgeSide}>
          <View style={[styles.badge, { backgroundColor: palette.dosePendingBadgeBg }]}>
            <FontAwesome name="clock-o" size={15} color={palette.dosePendingBadgeText} />
            <ThemedText
              style={[styles.badgeText, { color: palette.dosePendingBadgeText }]}
              maxFontSizeMultiplier={1.45}>
              {t('today.notTakenYet')}
            </ThemedText>
          </View>
        </View>

        <Pressable
          accessibilityRole="button"
          accessibilityLabel={listenA11y ?? listenLabel}
          accessibilityHint={t('a11y.listenTopHint')}
          disabled={listenDisabled}
          onPress={onListen}
          style={({ pressed }) => [
            styles.listenTop,
            {
              borderColor: palette.tint,
              backgroundColor: palette.background,
              opacity: listenDisabled ? 0.55 : pressed ? 0.88 : 1,
            },
          ]}>
          <FontAwesome name="volume-up" size={18} color={palette.tint} />
          <Text
            style={[styles.listenTopLabel, { color: palette.tint }]}
            numberOfLines={2}
            maxFontSizeMultiplier={1.55}>
            {listenLabel}
          </Text>
        </Pressable>
      </View>

      <ThemedText style={[styles.section, { color: palette.text }]} maxFontSizeMultiplier={1.5}>
        {sectionTitle}
      </ThemedText>
      <ThemedText style={[styles.medName, { color: palette.text }]} maxFontSizeMultiplier={1.5}>
        · {medicationName}
      </ThemedText>

      <LargeButton
        label={markTakenLabel}
        accessibilityLabel={markTakenA11y}
        style={styles.markTakenButton}
        onPress={onMarkTaken}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 16,
    borderLeftWidth: 5,
    paddingVertical: 16,
    paddingHorizontal: 16,
    paddingLeft: 14,
    marginBottom: 16,
    width: '100%',
    maxWidth: 520,
    alignSelf: 'center',
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 10,
    marginBottom: 14,
  },
  badgeSide: {
    flex: 1,
    minWidth: 0,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 8,
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 10,
  },
  badgeText: {
    fontSize: 16,
    fontWeight: '800',
    letterSpacing: 0.2,
  },
  listenTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: MIN_TOUCH,
    minWidth: MIN_TOUCH,
    maxWidth: '46%',
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 12,
    borderWidth: 2,
    gap: 8,
    flexShrink: 0,
  },
  listenTopLabel: {
    fontSize: 16,
    fontWeight: '700',
    flexShrink: 1,
    textAlign: 'right',
  },
  section: {
    fontSize: fontSize.body,
    fontWeight: '700',
    marginBottom: 8,
  },
  medName: {
    fontSize: fontSize.body,
    marginBottom: 16,
    lineHeight: 30,
    fontWeight: '600',
  },
  markTakenButton: {
    alignSelf: 'stretch',
  },
});
