// src/hooks/useAgent.ts
/**
 * Custom hook for managing agent state
 * 
 * Key features:
 * - Supports switching sessions without interrupting ongoing streaming
 * - Background streaming continues even when user switches away
 * - Seamless restoration when switching back to a streaming conversation
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type {
  Message,
  AgentSessionResponse,
  AgentHistoryResponse,
  ImageData,
} from '../types';
import {
  streamAgentChat,
  listAgentSessions,
  getAgentSessionHistory,
  deleteAgentSession,
  updateAgentSessionTitle
} from '../services/api/agent';
import { generateId, waitForNextTick } from '../utils';
import { STORAGE_KEYS } from '../constants';

// Type for streaming state cache
interface StreamingState {
  sessionId: string;
  messages: Message[];
  isStreaming: boolean;
  tempId?: string; // present when a new conversation hasn't received a server id yet
  abortController?: AbortController; // controller for this conversation's stream
}

// Helper functions for localStorage streaming cache
const saveStreamingCache = (cache: Map<string, StreamingState>) => {
  try {
    // Don't save abortController to localStorage (not serializable)
    const data = Array.from(cache.entries()).map(([key, state]) => [
      key,
      {
        sessionId: state.sessionId,
        messages: state.messages,
        isStreaming: state.isStreaming,
        tempId: state.tempId,
      },
    ]);
    localStorage.setItem(STORAGE_KEYS.STREAMING_CACHE, JSON.stringify(data));
  } catch (e) {
    console.warn('Failed to save streaming cache to localStorage:', e);
  }
};

const loadStreamingCache = (): Map<string, StreamingState> => {
  try {
    const data = localStorage.getItem(STORAGE_KEYS.STREAMING_CACHE);
    if (!data) return new Map();
    const entries = JSON.parse(data) as Array<[string, Omit<StreamingState, 'abortController'>]>;
    // Restore Date objects in messages, mark as not streaming since we lost connection
    return new Map(
      entries.map(([key, state]) => [
        key,
        {
          ...state,
          messages: state.messages.map(msg => ({
            ...msg,
            timestamp: new Date(msg.timestamp),
            isStreaming: false,
          })),
        },
      ])
    );
  } catch (e) {
    console.warn('Failed to load streaming cache from localStorage:', e);
    return new Map();
  }
};

const clearStreamingCache = (conversationId?: string) => {
  try {
    if (conversationId) {
      const cache = loadStreamingCache();
      cache.delete(conversationId);
      saveStreamingCache(cache);
    } else {
      localStorage.removeItem(STORAGE_KEYS.STREAMING_CACHE);
    }
  } catch (e) {
    console.warn('Failed to clear streaming cache:', e);
  }
};

// Agent specific constants
const AGENT_SESSIONS_PAGE_SIZE = 50;

// Helper to transform SSE events to TraceStep format
interface TraceStep {
  error: string | null;
  action: string;
  content: string | number | boolean | object | null;
  iteration: number;
  timestamp: string;
  tool_calls?: {
    name: string;
    arguments: Record<string, unknown>;
  }[];
  source?: 'agent' | 'subagent';
  subagent_name?: string;
}

function transformEventToTraceStep(event: any, fallbackIteration: number): TraceStep | null {
  switch (event.type) {
    case 'tool_call':
      return {
        error: null,
        action: 'tool_call',
        content: null,
        iteration: event.iteration ?? fallbackIteration,
        timestamp: new Date().toISOString(),
        tool_calls: [{
          name: event.name,
          arguments: event.arguments || {},
        }],
        source: event.source || 'agent',
        subagent_name: event.subagent_name,
      };
    case 'tool_result':
      return {
        error: event.error || null,
        action: 'tool_result',
        content: event.result,
        iteration: event.iteration ?? fallbackIteration,
        timestamp: new Date().toISOString(),
        tool_calls: [{
          name: event.name,
          arguments: {},
        }],
        source: event.source || 'agent',
        subagent_name: event.subagent_name,
      };
    case 'trace':
      return {
        error: event.error || null,
        action: event.action || 'unknown',
        content: event.content || null,
        iteration: event.iteration ?? fallbackIteration,
        timestamp: event.timestamp || new Date().toISOString(),
        tool_calls: event.tool_calls,
        source: event.source || 'agent',
        subagent_name: event.subagent_name,
      };
    default:
      return null;
  }
}

export function useAgent(token?: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [sessions, setSessions] = useState<AgentSessionResponse[]>([]);
  const [totalSessions, setTotalSessions] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pagination state
  const [sessionOffset, setSessionOffset] = useState(0);
  const [hasMoreSessions, setHasMoreSessions] = useState(true);

  // Cache for streaming state - supports multiple concurrent streaming conversations
  // Initialize from localStorage if available
  const streamingCacheRef = useRef<Map<string, StreamingState>>(loadStreamingCache());

  // Refs to access current state in callbacks
  const currentSessionIdRef = useRef<string | undefined>(sessionId);
  useEffect(() => { currentSessionIdRef.current = sessionId; }, [sessionId]);

  const setMessagesRef = useRef(setMessages);
  useEffect(() => { setMessagesRef.current = setMessages; }, [setMessages]);

  const setIsStreamingRef = useRef(setIsStreaming);
  useEffect(() => { setIsStreamingRef.current = setIsStreaming; }, [setIsStreaming]);

  const setSessionsRef = useRef(setSessions);
  useEffect(() => { setSessionsRef.current = setSessions; }, [setSessions]);

  const setSessionIdRef = useRef(setSessionId);
  useEffect(() => { setSessionIdRef.current = setSessionId; }, [setSessionId]);

  // Ref for refreshSessions to avoid stale closure in sendMessage
  const refreshSessionsRef = useRef<((reset?: boolean) => Promise<void>) | null>(null);

  const refreshSessions = useCallback(
    async (reset = true) => {
      try {
        const nextOffset = reset ? 0 : sessionOffset;
        const response = await listAgentSessions(
          token,
          AGENT_SESSIONS_PAGE_SIZE,
          nextOffset,
        );

        if (reset) {
          setSessions(response.sessions);
          setSessionOffset(AGENT_SESSIONS_PAGE_SIZE);
        } else {
          setSessions(prev => [...prev, ...response.sessions]);
          setSessionOffset(prev => prev + AGENT_SESSIONS_PAGE_SIZE);
        }

        setTotalSessions(response.total_count);
        setHasMoreSessions(nextOffset + response.sessions.length < response.total_count);
      } catch (err) {
        console.error('Failed to list agent sessions:', err);
      }
    },
    [sessionOffset, token]
  );

  // Update ref whenever refreshSessions changes
  useEffect(() => {
    refreshSessionsRef.current = refreshSessions;
  }, [refreshSessions]);

  // Separate function for initial load to avoid circular dependency
  const initialLoadSessions = useCallback(async () => {
    try {
      const response = await listAgentSessions(
        token,
        AGENT_SESSIONS_PAGE_SIZE,
        0,
      );
      setSessions(response.sessions);
      setSessionOffset(AGENT_SESSIONS_PAGE_SIZE);
      setTotalSessions(response.total_count);
      setHasMoreSessions(response.sessions.length < response.total_count);
    } catch (err) {
      console.error('Failed to list agent sessions:', err);
    }
  }, [token]);

  const loadMoreSessions = useCallback(async () => {
    if (!hasMoreSessions) return;
    await refreshSessions(false);
  }, [hasMoreSessions, refreshSessions]);

  // Initial load only when token changes
  useEffect(() => {
    if (token) {
      // Reset pagination and load first page
      setSessionOffset(0);
      setHasMoreSessions(true);
      initialLoadSessions();
    } else {
      setSessions([]);
      setTotalSessions(0);
    }
  }, [token, initialLoadSessions]);

  const mapHistoryToMessages = useCallback(
    (history: AgentHistoryResponse['messages']): Message[] => {
      return history.map((msg) => {
        const baseMessage: Message = {
          id: msg.id,
          role: msg.role as Message['role'],
          content: msg.content,
          timestamp: new Date(msg.created_at),
          trace: msg.trace,
        };

        // Extract image URLs from trace for user messages
        // (trace is reused to store image URLs for user messages)
        if (msg.role === 'user' && msg.trace && Array.isArray(msg.trace)) {
          const imageSources = msg.trace.filter(
            (s: { type?: string }) => s.type === 'image'
          );
          console.log(imageSources);
          if (imageSources.length > 0) {
            baseMessage.images = imageSources.map(
              (s: { url?: string; thumb_url?: string }) => s.thumb_url || s.url || ''
            ).filter(Boolean);
          }
        }

        // Add timing information if available (from database)
        // Use type assertion since these fields exist in API response but may not be in type definition
        const msgWithTiming = msg as typeof msg & {
          thinking_duration_ms?: number;
          answer_duration_ms?: number;
        };
        if (msgWithTiming.thinking_duration_ms !== undefined) {
          (baseMessage as any).thinking_duration_ms = msgWithTiming.thinking_duration_ms;
        }
        if (msgWithTiming.answer_duration_ms !== undefined) {
          (baseMessage as any).answer_duration_ms = msgWithTiming.answer_duration_ms;
        }

        return baseMessage;
      });
    },
    []
  );

  const sendMessage = useCallback(async (content: string, selectedTools?: string[], images?: ImageData[]) => {
    if (!content.trim() && (!images || images.length === 0)) return;
    if (isLoading) return;
    if (!token) {
      setError('Please log in to start chatting.');
      return;
    }

    setError(null);
    setIsLoading(true);
    setIsStreaming(true);

    const abortController = new AbortController();

    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: content.trim(),
      timestamp: new Date(),
      images: images?.map(img => `data:${img.mime_type};base64,${img.data}`),
    };

    const assistantMessageId = generateId();
    const thinkingStartTime = Date.now();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
      trace: [],
      thinkingStartTime, // Set the start time immediately
    };

    let streamingSessionId = sessionId ?? `temp-${assistantMessageId}`;
    const isTempSession = !sessionId;

    const currentMessages = messages;
    const initialMessages = [...currentMessages, userMessage, assistantMessage];
    setMessages(initialMessages);

    streamingCacheRef.current.set(streamingSessionId, {
      sessionId: streamingSessionId,
      messages: initialMessages,
      isStreaming: true,
      tempId: isTempSession ? streamingSessionId : undefined,
      abortController,
    });
    saveStreamingCache(streamingCacheRef.current);

    if (isTempSession) {
      setSessionId(streamingSessionId);
      // Provisional entry
      setSessions(prev => {
        if (prev.find(c => c.id === streamingSessionId)) return prev;
        return [
          {
            id: streamingSessionId,
            user_id: '', // Placeholder
            title: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            message_count: 0,
            last_message_preview: content.trim().substring(0, 80), // Use user's message as preview
          },
          ...prev,
        ];
      });
    }

    // Helper function to update streaming state for this session
    const updateStreamingState = (
      updater: (messages: Message[]) => Message[],
      streaming: boolean
    ) => {
      const cached = streamingCacheRef.current.get(streamingSessionId);
      if (!cached) return;

      const updatedMessages = updater(cached.messages);
      const updatedState = {
        ...cached,
        messages: updatedMessages,
        isStreaming: streaming,
      };
      streamingCacheRef.current.set(streamingSessionId, updatedState);
      saveStreamingCache(streamingCacheRef.current);

      // Only update UI if this conversation is currently displayed
      if (currentSessionIdRef.current === streamingSessionId) {
        setMessagesRef.current(updatedMessages);
        setIsStreamingRef.current(streaming);
      }
    };

    // Timing tracking - thinkingStartTime is already set in assistantMessage
    let answerStartTime: number | undefined;

    try {
      for await (const event of streamAgentChat({
        message: content,
        session_id: sessionId,
        agent_name: 'default',
        stream: true,
        selected_tools: selectedTools,
        images: images,
      }, token, abortController.signal)) {

        if (abortController.signal.aborted) break;

        switch (event.type) {
          case 'tool_call':
          case 'tool_result':
          case 'trace': {
            // Transform SSE event to TraceStep format
            const traceStep = transformEventToTraceStep(event, 0);
            if (traceStep) {
              updateStreamingState(
                msgs => msgs.map(msg =>
                  msg.id === assistantMessageId
                    ? { ...msg, trace: [...(msg.trace || []), traceStep] }
                    : msg
                ),
                true
              );
            }
            break;
          }

          case 'session':
            // Session info received early - we handle the actual ID switch in 'done'
            break;

          case 'text':
            // Record answer start time on first text event
            if (!answerStartTime) {
              answerStartTime = Date.now();
            }
            updateStreamingState(
              msgs => msgs.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, content: msg.content + (event.content || '') }
                  : msg
              ),
              true
            );
            break;

           case 'error':
             console.error('Agent error:', event.error);
             setError(event.error || 'An error occurred');
             // Stop streaming on error
             updateStreamingState(
               msgs => msgs.map(msg =>
                 msg.id === assistantMessageId
                   ? { ...msg, isStreaming: false }
                   : msg
               ),
               false
             );
             break;

          case 'done':
            {
              // Record answer end time
              const answerEndTime = Date.now();

              // Build timing data
              const timingData: Partial<Message> = {
                isStreaming: false,
                thinkingStartTime,
                thinkingEndTime: answerStartTime || answerEndTime,
                answerStartTime: answerStartTime,
                answerEndTime: answerEndTime,
              };

              // Save the original session ID before potential switch
              const originalSessionId = streamingSessionId;

              // Handle session ID switch for new sessions
              if (event.session_id) {
                const newId = event.session_id;
                if (isTempSession && streamingSessionId !== newId) {
                  const cached = streamingCacheRef.current.get(streamingSessionId);
                  if (cached) {
                    streamingCacheRef.current.delete(streamingSessionId);
                    streamingCacheRef.current.set(newId, { ...cached, sessionId: newId, tempId: streamingSessionId });
                  }

                  // Update session with proper last_message_preview
                  setSessionsRef.current(prev =>
                    prev.map(c => {
                      if (c.id === streamingSessionId) {
                        return {
                          ...c,
                          id: newId,
                          // Keep the last_message_preview from temp session (user's message)
                          last_message_preview: c.last_message_preview
                        };
                      }
                      return c;
                    })
                  );

                  // Update streamingSessionId first
                  streamingSessionId = newId;

                  // Then update the current session ID ref and state if this is the current session
                  if (currentSessionIdRef.current === originalSessionId) {
                    currentSessionIdRef.current = newId;
                    setSessionIdRef.current(newId);
                  }
                }
                // Delay refresh to allow backend to save messages
                setTimeout(() => refreshSessionsRef.current?.(true), 5);
              }

              const cached = streamingCacheRef.current.get(streamingSessionId);
              const finalMessages = cached
                ? cached.messages.map(msg =>
                    msg.id === assistantMessageId
                      ? { ...msg, ...timingData }
                      : msg
                  )
                : [];

              // Check both the new session ID and the original (for cases where session wasn't switched)
              if ((currentSessionIdRef.current === streamingSessionId || currentSessionIdRef.current === originalSessionId) && finalMessages.length > 0) {
                setMessagesRef.current(finalMessages);
                setIsStreamingRef.current(false);
              }
              streamingCacheRef.current.delete(streamingSessionId);
              saveStreamingCache(streamingCacheRef.current);
            }
            break;
        }

        await waitForNextTick();
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        // Handle abort - user stopped generation
      } else {
        console.error('Failed to send agent message:', err);
        if (currentSessionIdRef.current === streamingSessionId) {
          setError(err instanceof Error ? err.message : 'Failed to send message');
          setMessages(prev => prev.filter(msg => msg.id !== assistantMessageId));
        }
        // Stop streaming on error
        const cached = streamingCacheRef.current.get(streamingSessionId);
        if (cached) {
          const updatedMessages = cached.messages.map(msg =>
            msg.id === assistantMessageId
              ? { ...msg, isStreaming: false }
              : msg
          );
          streamingCacheRef.current.set(streamingSessionId, {
            ...cached,
            messages: updatedMessages,
            isStreaming: false,
          });
          saveStreamingCache(streamingCacheRef.current);
          
          // Update UI if this session is currently displayed
          if (currentSessionIdRef.current === streamingSessionId) {
            setMessagesRef.current(updatedMessages);
            setIsStreamingRef.current(false);
          }
        }
        streamingCacheRef.current.delete(streamingSessionId);
        if (isTempSession) {
          setSessionsRef.current(prev => prev.filter(c => c.id !== streamingSessionId));
        }
      }
    } finally {
      if (currentSessionIdRef.current === streamingSessionId) {
        setIsLoading(false);
        setIsStreaming(false);
      }
    }
  }, [sessionId, isLoading, token, messages]);

  const selectSession = useCallback(async (id: string) => {
    if (!id) return;

    // Check if we have cached streaming state for this conversation
    const cachedState = streamingCacheRef.current.get(id);
    if (cachedState && cachedState.isStreaming) {
      // Only restore from cache if streaming is STILL IN PROGRESS
      // If isStreaming is false, it means the connection was lost (e.g., page refresh)
      // and we should load fresh data from server instead of using stale cache
      setSessionId(cachedState.sessionId);
      setMessages(cachedState.messages);
      setIsStreaming(cachedState.isStreaming);
      setIsLoading(cachedState.isStreaming);
      setError(null);
      return;
    }

    // Clear any stale cache for this session (isStreaming=false means connection was lost)
    if (cachedState && !cachedState.isStreaming) {
      streamingCacheRef.current.delete(id);
      clearStreamingCache(id);
    }

    // Check if this is a temporary ID (not yet created on server)
    if (id.startsWith('temp-')) {
      setSessionId(undefined);
      setMessages([]);
      setError('This conversation has not been saved yet.');
      return;
    }

    // Reset streaming state when switching to a non-cached conversation
    setIsStreaming(false);
    setIsLoading(true);
    setError(null);
    try {
      const history = await getAgentSessionHistory(id, token);
      history.messages = history.messages.filter(
        (msg) => !(msg.role === 'assistant' && msg.content.trim() === '' && !msg.trace)
      );
      setSessionId(history.session_id);
      setMessages(mapHistoryToMessages(history.messages));
    } catch (err) {
      console.error('Failed to load agent session:', err);
      setError(err instanceof Error ? err.message : 'Failed to load session');
    } finally {
      setIsLoading(false);
    }
  }, [mapHistoryToMessages, token]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setSessionId(undefined);
    setError(null);
    setIsStreaming(false);
    setIsLoading(false);
  }, []);

  const removeSession = useCallback(async (id: string) => {
    if (!id || !token) return false;

    // Handle temp conversations (not yet saved to server)
    if (id.startsWith('temp-')) {
      const cached = streamingCacheRef.current.get(id);
      if (cached?.abortController) {
        cached.abortController.abort();
      }
      streamingCacheRef.current.delete(id);
      clearStreamingCache(id);
      setSessions(prev => prev.filter(c => c.id !== id));
      if (sessionId === id) {
        setMessages([]);
        setSessionId(undefined);
      }
      return true;
    }

    try {
      const cached = streamingCacheRef.current.get(id);
      if (cached?.abortController) {
        cached.abortController.abort();
      }

      await deleteAgentSession(id, token);
      streamingCacheRef.current.delete(id);
      clearStreamingCache(id);
      await initialLoadSessions();
      if (sessionId === id) {
        setMessages([]);
        setSessionId(undefined);
      }
      return true;
    } catch (err) {
      console.error('Failed to delete session:', err);
      setError(err instanceof Error ? err.message : 'Failed to delete session');
      return false;
    }
  }, [sessionId, token, initialLoadSessions]);

  const renameSession = useCallback(async (id: string, newTitle: string) => {
    if (!id || !token) return false;
    try {
      await updateAgentSessionTitle(id, newTitle, token);
      setSessions(prev =>
        prev.map(conv =>
          conv.id === id ? { ...conv, title: newTitle } : conv
        )
      );
      return true;
    } catch (err) {
      console.error('Failed to rename session:', err);
      setError(err instanceof Error ? err.message : 'Failed to rename session');
      return false;
    }
  }, [token]);

  return {
    messages,
    sessionId,
    sessions,
    totalSessions,
    hasMoreSessions,
    isLoading,
    isStreaming,
    error,
    sendMessage,
    selectSession,
    refreshSessions,
    loadMoreSessions,
    clearMessages,
    stopGeneration: () => {
      if (sessionId) {
        const cached = streamingCacheRef.current.get(sessionId);
        if (cached?.abortController) {
          cached.abortController.abort();
        }
      }
      setIsLoading(false);
      setIsStreaming(false);
      setMessages(prev =>
        prev.map(msg =>
          msg.isStreaming ? { ...msg, isStreaming: false } : msg
        )
      );
    },
    removeSession,
    renameSession,
  };
}
