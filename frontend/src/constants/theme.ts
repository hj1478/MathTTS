import { Platform, useColorScheme } from 'react-native';

const light = {
  text: '#1B1D1F',
  textSecondary: '#5F656D',
  background: '#F7F6F3',
  card: '#FFFFFF',
  border: '#E3E1DC',
  accent: '#2F5D50',
  accentText: '#FFFFFF',
  accentSoft: '#E4EEEA',
  danger: '#B3261E',
  dangerSoft: '#FBEAE8',
};

const dark: typeof light = {
  text: '#ECEDEE',
  textSecondary: '#A3A8AE',
  background: '#121314',
  card: '#1C1E20',
  border: '#2E3134',
  accent: '#7FC0AC',
  accentText: '#0E1A16',
  accentSoft: '#1F2E29',
  danger: '#F2B8B5',
  dangerSoft: '#3A1F1D',
};

export type Theme = typeof light;

export function useTheme(): Theme {
  return useColorScheme() === 'dark' ? dark : light;
}

export const Fonts = {
  sans: Platform.select({ web: 'Pretendard, system-ui, sans-serif', default: undefined }),
  mono: Platform.select({ web: 'ui-monospace, Menlo, monospace', ios: 'Menlo', default: 'monospace' }),
};

export const MaxContentWidth = 640;
