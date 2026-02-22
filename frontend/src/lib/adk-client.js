const API_BASE = '/api';
const APP_NAME = 'app';

export async function createSession(userId, sessionId, initialState = {}) {
  const res = await fetch(
    `${API_BASE}/apps/${APP_NAME}/users/${userId}/sessions/${sessionId}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(initialState),
    }
  );
  if (!res.ok) {
    const text = await res.text();
    if (text.includes('already exists')) return getSession(userId, sessionId);
    throw new Error(`Create session failed: ${text}`);
  }
  return res.json();
}

export async function getSession(userId, sessionId) {
  const res = await fetch(
    `${API_BASE}/apps/${APP_NAME}/users/${userId}/sessions/${sessionId}`
  );
  if (!res.ok) return null;
  return res.json();
}

export async function listSessions(userId) {
  const res = await fetch(
    `${API_BASE}/apps/${APP_NAME}/users/${userId}/sessions`
  );
  if (!res.ok) return [];
  const data = await res.json();
  return Array.isArray(data) ? data : data.sessions || [];
}

export async function deleteSession(userId, sessionId) {
  await fetch(
    `${API_BASE}/apps/${APP_NAME}/users/${userId}/sessions/${sessionId}`,
    { method: 'DELETE' }
  );
}

export async function getArtifact(userId, sessionId, artifactName) {
  const res = await fetch(
    `${API_BASE}/apps/${APP_NAME}/users/${userId}/sessions/${sessionId}/artifacts/${artifactName}`
  );
  if (!res.ok) return null;
  return res.json();
}

/**
 * Send a message to the agent via SSE streaming.
 * @param {string} userId
 * @param {string} sessionId
 * @param {string} text - User text message
 * @param {string|null} imageBase64 - Base64 encoded image (no prefix)
 * @param {string} imageMime - MIME type of image
 * @param {function} onToken - Called with each text chunk
 * @param {function} onArtifact - Called with artifact name when delta received
 * @param {function} onDone - Called when stream completes
 * @param {function} onError - Called on error
 * @returns {AbortController} - To cancel the stream
 */
export function sendMessageSSE(
  userId,
  sessionId,
  text,
  imageBase64 = null,
  imageMime = 'image/jpeg',
  { onToken, onArtifact, onDone, onError }
) {
  const controller = new AbortController();

  const parts = [];
  if (text) parts.push({ text });
  if (imageBase64) {
    parts.push({
      inlineData: {
        data: imageBase64,
        mimeType: imageMime,
      },
    });
  }

  const body = {
    appName: APP_NAME,
    userId,
    sessionId,
    newMessage: {
      role: 'user',
      parts,
    },
    streaming: true,
  };

  fetch(`${API_BASE}/run_sse`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const errText = await res.text();
        onError?.(new Error(`SSE request failed: ${errText}`));
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.slice(6).trim();
          if (!jsonStr || jsonStr === '[DONE]') continue;

          try {
            const event = JSON.parse(jsonStr);

            // Extract text from content parts
            if (event.content?.parts) {
              for (const part of event.content.parts) {
                if (part.text) {
                  fullText += part.text;
                  onToken?.(part.text, fullText);
                }
              }
            }

            // Track artifact deltas
            if (event.actions?.artifactDelta) {
              for (const name of Object.keys(event.actions.artifactDelta)) {
                onArtifact?.(name);
              }
            }
          } catch {
            // Skip malformed JSON lines
          }
        }
      }

      onDone?.(fullText);
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError?.(err);
      }
    });

  return controller;
}

/**
 * Send a message without streaming (simpler, for fallback).
 */
export async function sendMessage(userId, sessionId, text, imageBase64 = null, imageMime = 'image/jpeg') {
  const parts = [];
  if (text) parts.push({ text });
  if (imageBase64) {
    parts.push({
      inlineData: {
        data: imageBase64,
        mimeType: imageMime,
      },
    });
  }

  const res = await fetch(`${API_BASE}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      appName: APP_NAME,
      userId,
      sessionId,
      newMessage: { role: 'user', parts },
      streaming: false,
    }),
  });

  if (!res.ok) throw new Error(`Run failed: ${await res.text()}`);
  return res.json();
}
