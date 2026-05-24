/**
 * Conversation API services
 */

import { API_BASE } from '../../constants';
import { createAuthHeaders, createJsonHeaders, parseErrorResponse } from './client';
import type {
  ConversationRequest,
  ConversationHistoryResponse,
  ConversationListResponse,
  SSEEvent,
} from '../../types';

/**
 * Send a message and receive streaming response
 */
export async function* streamConversation(
  request: ConversationRequest,
  token?: string,
  signal?: AbortSignal
): AsyncGenerator<SSEEvent> {
  const response = await fetch(`${API_BASE}/conversation`, {
    method: 'POST',
    headers: createJsonHeaders(token),
    body: JSON.stringify({
      ...request,
      stream: true,
    }),
    signal,
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      // Check if aborted before reading
      if (signal?.aborted) {
        break;
      }

      const { done, value } = await reader.read();
      
      if (done) {
        // Process any remaining data in buffer before exiting
        if (buffer.trim()) {
          const remainingLines = buffer.split('\n');
          for (const line of remainingLines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                yield data as SSEEvent;
              } catch (e) {
                console.warn('Failed to parse final SSE event:', line);
              }
            }
          }
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      
      // Process complete SSE events
      const lines = buffer.split('\n');
      buffer = lines.pop() || ''; // Keep incomplete line in buffer

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            yield data as SSEEvent;
          } catch (e) {
            console.warn('Failed to parse SSE event:', line);
          }
        }
      }
    }
  } finally {
    // Cancel the reader to properly close the underlying connection
    // This is important for freeing up browser connection slots
    try {
      await reader.cancel();
    } catch {
      // Ignore cancel errors
    }
    reader.releaseLock();
  }
}

/**
 * Get conversation history
 */
export async function getConversationHistory(
  conversationId: string,
  token?: string
): Promise<ConversationHistoryResponse> {
  const response = await fetch(`${API_BASE}/conversation/${conversationId}`, {
    headers: createAuthHeaders(token),
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * List conversations with pagination
 */
export async function listConversations(
  token?: string,
  limit: number = 50,
  offset: number = 0
): Promise<ConversationListResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
    offset: offset.toString(),
  });
  
  const response = await fetch(`${API_BASE}/conversation?${params}`, {
    headers: createAuthHeaders(token),
  });

  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

/**
 * Delete a conversation
 */
export async function deleteConversation(
  conversationId: string,
  token?: string
): Promise<{ success: boolean }> {
  const response = await fetch(`${API_BASE}/conversation/${conversationId}`, {
    method: 'DELETE',
    headers: createAuthHeaders(token),
  });
  
  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }
  
  return response.json();
}

/**
 * Update conversation title
 */
export async function updateConversationTitle(
  conversationId: string,
  title: string,
  token?: string
): Promise<{ success: boolean }> {
  const response = await fetch(`${API_BASE}/conversation/${conversationId}/title`, {
    method: 'PUT',
    headers: createJsonHeaders(token),
    body: JSON.stringify({ title }),
  });
  
  if (!response.ok) {
    const msg = await parseErrorResponse(response);
    throw new Error(msg || `HTTP error! status: ${response.status}`);
  }
  
  return response.json();
}
