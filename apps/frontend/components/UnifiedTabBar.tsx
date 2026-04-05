import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import { useTranslation } from 'react-i18next';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import Colors from '@/constants/Colors';
import { useVoiceRecording } from '@/hooks/useVoiceRecording';
import { useColorScheme } from '@/components/useColorScheme';

const MIC_SIZE = 64;
const MIC_ICON = 30;
/** Outer tabs (Home, Settings) — compact */
const TAB_ICON_SIDE = 21;
/** Medications & Family in the arc cluster */
const TAB_ICON_ARC = 28;
/**
 * Arc: only the icons shift — labels stay on one baseline.
 * Negative translateY lifts icons (wings below mic peak).
 */
const ARC_WING_LIFT = -8;
const ARC_MIC_LIFT = -12;

/** Approximate dock height for scroll padding — keep in sync with styles.dock */
export const UNIFIED_TAB_BAR_BASE_HEIGHT = 118;

export function UnifiedTabBar({ state, descriptors, navigation }: BottomTabBarProps) {
  const insets = useSafeAreaInsets();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];
  const { recording, onPressIn, onPressOut } = useVoiceRecording();

  const routes = state.routes;
  const homeRoute = routes[0];
  const medicationsRoute = routes[1];
  const familyRoute = routes[2];
  const settingsRoute = routes[3];

  const bottomInset = Math.max(insets.bottom, Platform.OS === 'android' ? 10 : 8);

  const renderTab = (
    route: (typeof routes)[0],
    opts: { variant: 'side' | 'arc'; arcTranslateY?: number },
  ) => {
    const { options } = descriptors[route.key];
    const routeIndex = state.routes.findIndex((r) => r.key === route.key);
    const isFocused = state.index === routeIndex;
    const color = isFocused ? palette.tint : palette.tabIconDefault;
    const iconSize = opts.variant === 'side' ? TAB_ICON_SIDE : TAB_ICON_ARC;

    const onPress = () => {
      const event = navigation.emit({
        type: 'tabPress',
        target: route.key,
        canPreventDefault: true,
      });
      if (!isFocused && !event.defaultPrevented) {
        navigation.navigate(route.name as never);
      }
    };

    const onLongPress = () => {
      navigation.emit({
        type: 'tabLongPress',
        target: route.key,
      });
    };

    const iconEl =
      options.tabBarIcon?.({
        focused: isFocused,
        color,
        size: iconSize,
      }) ?? null;

    const tabLabelText =
      typeof options.tabBarLabel === 'string'
        ? options.tabBarLabel
        : ((options.title ?? route.name) as string);

    const iconLift =
      opts.variant === 'arc' && opts.arcTranslateY != null
        ? { transform: [{ translateY: opts.arcTranslateY }] }
        : null;

    return (
      <Pressable
        key={route.key}
        accessibilityRole="button"
        accessibilityState={{ selected: isFocused }}
        accessibilityLabel={
          (options.tabBarAccessibilityLabel as string | undefined) ?? options.title
        }
        testID={options.tabBarButtonTestID}
        onPress={onPress}
        onLongPress={onLongPress}
        style={({ pressed }) => [
          opts.variant === 'side' ? styles.tabItemSide : styles.tabItemArc,
          { opacity: pressed ? 0.75 : 1 },
        ]}>
        <View
          style={[
            opts.variant === 'side' ? styles.tabIconWrapSide : styles.tabIconWrapArc,
            iconLift,
          ]}>
          {iconEl}
        </View>
        <Text
          numberOfLines={1}
          ellipsizeMode="tail"
          style={[
            opts.variant === 'side' ? styles.tabLabelSide : styles.tabLabelArc,
            { color },
            Platform.OS === 'android' ? { includeFontPadding: false } : null,
          ]}>
          {tabLabelText}
        </Text>
      </Pressable>
    );
  };

  const { t } = useTranslation();

  return (
    <View
      style={[
        styles.dockOuter,
        Platform.select({
          ios: {
            shadowColor: '#000',
            shadowOffset: { width: 0, height: -2 },
            shadowOpacity: 0.08,
            shadowRadius: 12,
          },
          android: { elevation: 16 },
          default: {},
        }),
      ]}>
      <View
        style={[
          styles.dock,
          {
            paddingBottom: bottomInset,
            backgroundColor: palette.dockBackground,
            borderColor: palette.dockBorder,
          },
        ]}>
        <View style={styles.row}>
          {renderTab(homeRoute, { variant: 'side' })}

          <View style={styles.arcCluster}>
            {renderTab(medicationsRoute, { variant: 'arc', arcTranslateY: ARC_WING_LIFT })}
            <View style={styles.voiceColumn}>
              <View style={[styles.micLift, { transform: [{ translateY: ARC_MIC_LIFT }] }]}>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={t('a11y.voiceHold')}
                  accessibilityHint={t('a11y.voiceHoldHint')}
                  onPressIn={onPressIn}
                  onPressOut={onPressOut}
                  style={({ pressed }) => [
                    styles.micOuter,
                    {
                      backgroundColor: recording ? palette.tint : palette.voiceButtonBg,
                      borderColor: palette.voiceButtonBorder,
                      opacity: pressed ? 0.92 : 1,
                    },
                  ]}>
                  <FontAwesome name="microphone" size={MIC_ICON} color={palette.onPrimary} />
                </Pressable>
              </View>
              <Text
                style={[styles.voiceCaption, { color: palette.textSecondary }]}
                maxFontSizeMultiplier={1.4}
                numberOfLines={1}
                ellipsizeMode="tail">
                {recording ? t('voice.releasing') : t('voice.holdToSpeak')}
              </Text>
            </View>
            {renderTab(familyRoute, { variant: 'arc', arcTranslateY: ARC_WING_LIFT })}
          </View>

          {renderTab(settingsRoute, { variant: 'side' })}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  dockOuter: {
    backgroundColor: 'transparent',
  },
  dock: {
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderLeftWidth: StyleSheet.hairlineWidth,
    borderRightWidth: StyleSheet.hairlineWidth,
    paddingTop: 18,
    paddingHorizontal: 6,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'space-between',
    minHeight: 82,
  },
  tabItemSide: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'flex-end',
    paddingBottom: 4,
    paddingHorizontal: 2,
  },
  tabItemArc: {
    flex: 1,
    minWidth: 0,
    alignItems: 'center',
    justifyContent: 'flex-end',
    paddingBottom: 4,
    paddingHorizontal: 4,
  },
  arcCluster: {
    flex: 2.2,
    flexDirection: 'row',
    alignItems: 'flex-end',
    justifyContent: 'center',
    minWidth: 0,
    gap: 8,
    paddingHorizontal: 0,
  },
  tabIconWrapSide: {
    marginBottom: 4,
    height: TAB_ICON_SIDE + 2,
    justifyContent: 'center',
  },
  tabIconWrapArc: {
    marginBottom: 4,
    height: TAB_ICON_ARC + 4,
    justifyContent: 'center',
  },
  tabLabelSide: {
    fontSize: 9,
    fontWeight: '700',
    textAlign: 'center',
    lineHeight: 12,
  },
  tabLabelArc: {
    fontSize: 10,
    fontWeight: '700',
    textAlign: 'center',
    lineHeight: 13,
  },
  micLift: {
    alignItems: 'center',
  },
  voiceColumn: {
    width: 88,
    flexShrink: 0,
    alignItems: 'center',
    justifyContent: 'flex-end',
    paddingBottom: 4,
  },
  voiceCaption: {
    fontSize: 10,
    fontWeight: '700',
    marginTop: 5,
    textAlign: 'center',
    lineHeight: 12,
  },
  micOuter: {
    width: MIC_SIZE,
    height: MIC_SIZE,
    borderRadius: MIC_SIZE / 2,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 3,
  },
});
