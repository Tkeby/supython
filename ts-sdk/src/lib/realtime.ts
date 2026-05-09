import { RealtimeClient as _RealtimeClient } from '@supabase/realtime-js';

export function createRealtimeClient(
  url: string,
  params: Record<string, string>,
): _RealtimeClient {
  return new _RealtimeClient(url, { params });
}

export type RealtimeClient = _RealtimeClient;
export type { RealtimeChannel } from '@supabase/realtime-js';
