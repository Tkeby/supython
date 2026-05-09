import { ref, shallowRef, onUnmounted } from "vue";

export function useLiveTail<T>(
  path: string,
  parse: (eventName: string, rawData: string) => T,
  eventNames?: string[],
) {
  const events = shallowRef<T[]>([]);
  const connected = ref(false);
  const paused = ref(false);

  const es = new EventSource(`/admin/api/v1${path}`, { withCredentials: true });

  es.onopen = () => {
    connected.value = true;
  };

  es.onerror = () => {
    connected.value = false;
  };

  const handleEvent = (name: string, data: string) => {
    if (paused.value) return;
    events.value = [...events.value, parse(name, data)];
    if (events.value.length > 1000) {
      events.value = events.value.slice(-1000);
    }
  };

  if (eventNames && eventNames.length > 0) {
    for (const name of eventNames) {
      es.addEventListener(name, (e: MessageEvent) => {
        handleEvent(name, e.data);
      });
    }
  } else {
    es.onmessage = (e) => {
      handleEvent("message", e.data);
    };
  }

  const pause = () => {
    paused.value = true;
  };

  const resume = () => {
    paused.value = false;
  };

  const clear = () => {
    events.value = [];
  };

  let closed = false;

  const close = () => {
    if (closed) return;
    closed = true;
    connected.value = false;
    es.close();
  };

  onUnmounted(() => close());

  return { events, connected, paused, pause, resume, clear, close };
}
