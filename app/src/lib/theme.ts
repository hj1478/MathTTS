// Tokens from design/ui/Tokens.dc.html. Contrast ratios are listed there.
import { Platform, useColorScheme, useWindowDimensions } from 'react-native';

const light = {
  bg: '#F5F6F8',
  surface: '#FFFFFF',
  surface2: '#EDF0F4',
  border: '#D3D8E0',
  borderStrong: '#7D8796',
  text: '#12161C',
  text2: '#475061',
  primary: '#1D4ED8',
  onPrimary: '#FFFFFF',
  primaryText: '#1D4ED8',
  primarySoft: '#E6ECFC',
  onPrimarySoft: '#1E3A8A',
  hlBg: '#FFE58A',
  hlText: '#12161C',
  hlLine: '#8A5A00',
  noteBg: '#FFF6E0',
  noteText: '#6B4500',
  noteBorder: '#E6C377',
  errorBg: '#FDECEC',
  errorText: '#9F1D1D',
  errorBorder: '#E8A3A3',
  infoBg: '#E8EEFB',
  infoText: '#1E3A8A',
  infoBorder: '#AFC2F0',
  success: '#15803D',
  focus: '#1D4ED8',
};

export type Colors = typeof light;

const dark: Colors = {
  bg: '#0E1116',
  surface: '#171B22',
  surface2: '#222833',
  border: '#323A48',
  borderStrong: '#7A8496',
  text: '#EDF0F4',
  text2: '#B3BBC7',
  primary: '#8EB1FF',
  onPrimary: '#0B1530',
  primaryText: '#9DBBFF',
  primarySoft: '#1C2A4A',
  onPrimarySoft: '#C9D8FF',
  hlBg: '#5C4A0E',
  hlText: '#FFF4CC',
  hlLine: '#F2C94C',
  noteBg: '#2A2210',
  noteText: '#F3D38B',
  noteBorder: '#5A4719',
  errorBg: '#3A1717',
  errorText: '#FFB3B3',
  errorBorder: '#7A3030',
  infoBg: '#172443',
  infoText: '#C3D3FF',
  infoBorder: '#34487A',
  success: '#6FD69A',
  focus: '#9DBBFF',
};

// On web the name is a CSS font-family list: if the font files fail to load,
// fall back to the system sans-serif, not the browser's default serif.
const family = (name: string) => (Platform.OS === 'web' ? `${name}, system-ui, sans-serif` : name);

export const font = {
  regular: family('IBMPlexSansKR_400Regular'),
  medium: family('IBMPlexSansKR_500Medium'),
  semibold: family('IBMPlexSansKR_600SemiBold'),
  bold: family('IBMPlexSansKR_700Bold'),
};

// Light by default, whatever the device is set to. Set to true to follow the
// system setting again (the dark tokens above are kept for that).
const FOLLOW_SYSTEM_THEME = false;

export function useScheme(): 'light' | 'dark' {
  const system = useColorScheme();
  return FOLLOW_SYSTEM_THEME && system === 'dark' ? 'dark' : 'light';
}

export function useColors(): Colors {
  return useScheme() === 'dark' ? dark : light;
}

/** Two-column layout from 960px (Tokens: 데스크톱 배치). */
export function useWide(): boolean {
  return useWindowDimensions().width >= 960;
}
