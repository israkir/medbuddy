import React from 'react';
import {
  Pressable,
  StyleSheet,
  type PressableProps,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { MIN_TOUCH } from '@/constants/accessibility';
import Colors from '@/constants/Colors';
import { Text } from '@/components/Themed';
import { useColorScheme } from '@/components/useColorScheme';

type Props = PressableProps & {
  label: string;
  variant?: 'primary' | 'secondary';
  style?: StyleProp<ViewStyle>;
  /** Use when the label may wrap (e.g. narrow top-corner buttons). */
  labelNumberOfLines?: number;
};

export function LargeButton({
  label,
  variant = 'primary',
  style,
  accessibilityLabel,
  labelNumberOfLines,
  ...rest
}: Props) {
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];
  const isPrimary = variant === 'primary';

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      style={({ pressed }) => [
        styles.base,
        {
          backgroundColor: isPrimary ? palette.tint : palette.background,
          borderColor: palette.tint,
          borderWidth: isPrimary ? 0 : 2,
          opacity: pressed ? 0.85 : 1,
        },
        style,
      ]}
      {...rest}>
      <Text
        style={[
          styles.label,
          { color: isPrimary ? palette.onPrimary : palette.tint, textAlign: 'center' },
        ]}
        maxFontSizeMultiplier={1.6}
        numberOfLines={labelNumberOfLines}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: MIN_TOUCH,
    paddingHorizontal: 20,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: {
    fontSize: 18,
    fontWeight: '600',
  },
});
