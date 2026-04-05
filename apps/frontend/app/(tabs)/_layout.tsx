import React from 'react';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import { Link, Tabs } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import { useTranslation } from 'react-i18next';

import { UnifiedTabBar } from '@/components/UnifiedTabBar';
import { MedicationExplanationProvider } from '@/context/MedicationExplanationContext';
import Colors from '@/constants/Colors';
import { useColorScheme } from '@/components/useColorScheme';
import { useClientOnlyValue } from '@/components/useClientOnlyValue';

function TabBarIcon(props: {
  name: React.ComponentProps<typeof FontAwesome>['name'];
  color: string;
  size?: number;
}) {
  const { size = 24, ...rest } = props;
  return <FontAwesome size={size} style={styles.tabIcon} {...rest} />;
}

export default function TabLayout() {
  const { t } = useTranslation();
  const colorScheme = useColorScheme();
  const palette = Colors[colorScheme ?? 'light'];

  return (
    <View style={styles.tabRoot}>
      <MedicationExplanationProvider>
      <Tabs
        tabBar={(props) => <UnifiedTabBar {...props} />}
        screenOptions={{
          tabBarShowLabel: false,
          headerShown: useClientOnlyValue(false, true),
        }}>
      <Tabs.Screen
        name="index"
        options={{
          title: t('tabs.today'),
          tabBarAccessibilityLabel: t('a11y.tabToday'),
          tabBarIcon: ({ color, size }) => <TabBarIcon name="home" color={color} size={size} />,
          headerRight: () => (
            <Link href="/modal" asChild>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={t('a11y.openInfo')}>
                {({ pressed }) => (
                  <FontAwesome
                    name="info-circle"
                    size={24}
                    color={palette.text}
                    style={{ marginRight: 16, opacity: pressed ? 0.5 : 1 }}
                  />
                )}
              </Pressable>
            </Link>
          ),
        }}
      />
      <Tabs.Screen
        name="medications"
        options={{
          title: t('medications.title'),
          tabBarLabel: t('tabs.medicationsDock'),
          tabBarAccessibilityLabel: t('a11y.tabMedications'),
          tabBarIcon: ({ color, size }) => <TabBarIcon name="medkit" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="family"
        options={{
          title: t('tabs.family'),
          tabBarAccessibilityLabel: t('a11y.tabFamily'),
          tabBarIcon: ({ color, size }) => <TabBarIcon name="users" color={color} size={size} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: t('tabs.settings'),
          tabBarAccessibilityLabel: t('a11y.tabSettings'),
          tabBarIcon: ({ color, size }) => <TabBarIcon name="cog" color={color} size={size} />,
        }}
      />
      </Tabs>
      </MedicationExplanationProvider>
    </View>
  );
}

const styles = StyleSheet.create({
  tabRoot: {
    flex: 1,
  },
  tabIcon: {
    marginBottom: 2,
  },
});
