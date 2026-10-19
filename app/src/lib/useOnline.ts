import { useNetworkState } from 'expo-network';

/** false only when the device is known to be offline. */
export function useOnline(): boolean {
  const s = useNetworkState();
  return !(s.isConnected === false || s.isInternetReachable === false);
}
