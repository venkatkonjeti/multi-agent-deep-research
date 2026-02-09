/* ─── API client for communicating with the FastAPI backend ─── */

import type { Conversation, Message, UploadResult, HealthStatus, TraceEvent } from './types';

const API_BASE = '/api';

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ─── Health ─────────────────────────────────────────────

export async function getHealth(): Promise<HealthStatus> {
  return apiFetch('/health');
}

// ─── Conversations ─────────────────────────────────────

export async function listConversations(): Promise<Conversation[]> {
  return apiFetch('/conversations');
}

export async function createConversation(title = 'New Conversation'): Promise<Conversation> {
  return apiFetch('/conversations', {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export async function deleteConversation(id: string): Promise<void> {
  await apiFetch(`/conversations/${id}`, { method: 'DELETE' });
}

export async function renameConversation(id: string, title: string): Promise<void> {
  await apiFetch(`/conversations/${id}`, {
    method: 'PUT',
    body: JSON.stringify({ title }),
  });
}

// ─── Messages ──────────────────────────────────────────

export async function getMessages(conversationId: string): Promise<Message[]> {
  return apiFetch(`/conversations/${conversationId}/messages`);
}

// ─── Chat (SSE) ────────────────────────────────────────

export interface ChatSSECallbacks {
  onTrace: (event: TraceEvent) => void;
  onToken: (token: string) => void;
  onFullResponse: (message: string) => void;
  onDone: () => void;
  onError: (error: string) => void;
}

export async function sendChatMessage(
  conversationId: string,
  message: string,
  callbacks: ChatSSECallbacks,
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId, message }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    callbacks.onError(err.detail || res.statusText);
    return;
  }

  const reader = res.body?.getReader();
  if (!reader) {
    callbacks.onError('No response body');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith('data: ')) continue;

      try {
        const data = JSON.parse(trimmed.slice(6));

        if (data.type === 'done') {
          callbacks.onDone();
        } else if (data.type === 'error') {
          callbacks.onError(data.message);
        } else if (data.type === 'full_response') {
          callbacks.onFullResponse(data.message);
        } else if (data.type === 'stream_token') {
          callbacks.onToken(data.message);
        } else {
          // Agent trace events
          callbacks.onTrace(data as TraceEvent);
        }
      } catch {
        // skip malformed JSON
      }
    }
  }
}

// ─── File Upload ───────────────────────────────────────

export async function uploadPDF(
  conversationId: string,
  file: File,
): Promise<UploadResult> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('conversation_id', conversationId);

  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }

  return res.json();
}
