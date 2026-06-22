/**
 * fetch Response에서 SSE를 파싱하는 async generator. §12.2
 *
 * 브라우저 EventSource는 GET 전용 → fetch + ReadableStream으로 직접 파싱.
 * 포맷: "event: <name>\ndata: <json>\n\n" 반복.
 */
export async function* streamSSE(
  response: Response,
): AsyncGenerator<{ event: string; data: unknown }> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // 이중 개행으로 메시지 경계 분리
      const messages = buffer.split('\n\n');
      buffer = messages.pop() ?? '';

      for (const msg of messages) {
        if (!msg.trim()) continue;

        let event = '';
        let data = '';

        for (const line of msg.split('\n')) {
          if (line.startsWith('event: ')) event = line.slice(7).trim();
          else if (line.startsWith('data: ')) data = line.slice(6).trim();
        }

        if (event && data) {
          try {
            yield { event, data: JSON.parse(data) };
          } catch {
            // malformed JSON 스킵
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
