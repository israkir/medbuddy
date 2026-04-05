/**
 * Theme tokens tuned for older adults: stronger contrast than typical “soft UI”,
 * warm page backgrounds (less harsh than pure white), and clear borders.
 *
 * Rough targets on `background`: body text ~7:1, secondary text ≥4.5:1 (WCAG AA).
 */

const light = {
  /** Headings & primary reading */
  text: '#171412',
  /** Hints, captions, tab captions — darker than typical muted gray */
  textSecondary: '#3f3f46',
  /** Warm paper tone — reduces glare vs #fff */
  background: '#fff8f2',
  /** Links, selected tabs, primary actions — teal-700 for strong contrast */
  tint: '#0f7669',
  /** Text/icons on primary-filled buttons (mic, solid CTAs) */
  onPrimary: '#ffffff',
  /** Inactive tab icons — clearly visible, not “washed out” */
  tabIconDefault: '#52525b',
  tabIconSelected: '#0f7669',
  /** Hold-to-speak — darker fill for icon contrast */
  voiceButtonBg: '#115e59',
  /** Tips / intro panels */
  voicePanelBg: '#ccfbf1',
  /** Schedule cards, medication rows */
  cardBackground: '#e0f2f1',
  /** Inset fields on medication list cards (high contrast on mint) */
  medicationFieldSurface: '#ffffff',
  medicationFieldBorder: 'rgba(15, 118, 105, 0.2)',
  /** Settings list selection */
  selectedBackground: 'rgba(15, 118, 105, 0.14)',
  /** Inputs, outlines, language rows */
  border: '#78716c',
  /** Dividers (modal, sections) */
  separator: '#d6d3d1',
  /** Bottom tab dock */
  dockBackground: 'rgba(255, 250, 245, 0.98)',
  dockBorder: 'rgba(15, 118, 105, 0.32)',
  /** Ring around mic */
  voiceButtonBorder: 'rgba(255, 255, 255, 0.95)',
  /**
   * Dose not yet marked — warm amber (attention + action, not error red).
   * Left border + surface read clearly on warm page background.
   */
  dosePendingSurface: '#fff7ed',
  dosePendingAccent: '#ea580c',
  dosePendingBadgeBg: '#ffedd5',
  dosePendingBadgeText: '#9a3412',
} as const;

const dark = {
  text: '#fafaf9',
  textSecondary: '#d4d4d8',
  background: '#0c0a09',
  tint: '#2dd4bf',
  /** Light icons/text on filled primary / voice controls */
  onPrimary: '#ffffff',
  tabIconDefault: '#a1a1aa',
  tabIconSelected: '#5eead4',
  voiceButtonBg: '#14b8a6',
  voicePanelBg: 'rgba(20, 83, 72, 0.55)',
  cardBackground: 'rgba(15, 118, 105, 0.38)',
  medicationFieldSurface: 'rgba(28, 25, 23, 0.92)',
  medicationFieldBorder: 'rgba(94, 234, 212, 0.22)',
  selectedBackground: 'rgba(45, 212, 191, 0.2)',
  border: '#57534e',
  separator: 'rgba(255, 255, 255, 0.16)',
  dockBackground: 'rgba(23, 20, 18, 0.98)',
  dockBorder: 'rgba(94, 234, 212, 0.28)',
  voiceButtonBorder: 'rgba(255, 255, 255, 0.35)',
  dosePendingSurface: 'rgba(251, 146, 60, 0.14)',
  dosePendingAccent: '#fb923c',
  dosePendingBadgeBg: 'rgba(194, 65, 12, 0.42)',
  dosePendingBadgeText: '#ffedd5',
} as const;

export type ThemeName = 'light' | 'dark';
export type ThemeColors = typeof light;

export default {
  light,
  dark,
};
