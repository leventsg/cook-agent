// src/hooks/useConversation.ts
/**
 * Custom hook for managing conversation state
 * 
 * Key features:
 * - Supports switching conversations without interrupting ongoing streaming
 * - Background streaming continues even when user switches away
 * - Seamless restoration when switching back to a streaming conversation
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type {
  Message,
  IntentInfo,
  VisionInfo,
  Source,
  ConversationSummary,
  ConversationHistoryResponse,
  ExtraOptions,
  ImageData,
} from '../types';
import {
  deleteConversation,
  getConversationHistory,
  listConversations,
  streamConversation,
  updateConversationTitle,
} from '../services/api';
import { STORAGE_KEYS, CONVERSATIONS_PAGE_SIZE } from '../constants';
import { generateId, waitForNextTick } from '../utils';

// Type for streaming state cache
interface StreamingState {
  conversationId: string;
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
        conversationId: state.conversationId,
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
    // Restore Date objects in messages, mark as not streaming since we lost the connection
    return new Map(
      entries.map(([key, state]) => [
        key,
        {
          ...state,
          // Mark as not streaming since the connection was lost on page reload
          isStreaming: false,
          messages: state.messages.map(msg => ({
            ...msg,
            timestamp: new Date(msg.timestamp),
            // Mark any streaming messages as complete since connection was lost
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

export function useConversation(token?: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [totalConversations, setTotalConversations] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Pagination state
  const [conversationOffset, setConversationOffset] = useState(0);
  const [hasMoreConversations, setHasMoreConversations] = useState(true);
  
  // Cache for streaming state - supports multiple concurrent streaming conversations
  // Initialize from localStorage if available
  const streamingCacheRef = useRef<Map<string, StreamingState>>(loadStreamingCache());
  
  // Track current conversation ID in a ref to access in streaming callbacks
  const currentConversationIdRef = useRef<string | undefined>(conversationId);
  useEffect(() => {
    currentConversationIdRef.current = conversationId;
  }, [conversationId]);
  
  // Ref for setMessages to use in streaming callbacks without stale closure
  const setMessagesRef = useRef(setMessages);
  useEffect(() => {
    setMessagesRef.current = setMessages;
  }, [setMessages]);
  
  // Ref for setIsStreaming
  const setIsStreamingRef = useRef(setIsStreaming);
  useEffect(() => {
    setIsStreamingRef.current = setIsStreaming;
  }, [setIsStreaming]);
  
  // Ref for setConversationId
  const setConversationIdRef = useRef(setConversationId);
  useEffect(() => {
    setConversationIdRef.current = setConversationId;
  }, [setConversationId]);
  
  // Ref for setConversations
  const setConversationsRef = useRef(setConversations);
  useEffect(() => {
    setConversationsRef.current = setConversations;
  }, [setConversations]);
  
  // Ref for refreshConversations to avoid stale closure in sendMessage
  const refreshConversationsRef = useRef<((reset?: boolean) => Promise<void>) | null>(null);

  const refreshConversations = useCallback(
    async (reset = true) => {
      try {
        const nextOffset = reset ? 0 : conversationOffset;
        const { conversations: list, total_count } = await listConversations(
          token,
          CONVERSATIONS_PAGE_SIZE,
          nextOffset,
        );

        if (reset) {
          setConversations(list);
          setConversationOffset(CONVERSATIONS_PAGE_SIZE);
        } else {
          setConversations(prev => [...prev, ...list]);
          setConversationOffset(prev => prev + CONVERSATIONS_PAGE_SIZE);
        }

        setTotalConversations(total_count);
        setHasMoreConversations(nextOffset + list.length < total_count);
      } catch (err) {
        console.error('Failed to list conversations:', err);
      }
    },
    [conversationOffset, token]
  );
  
  // Update ref whenever refreshConversations changes
  useEffect(() => {
    refreshConversationsRef.current = refreshConversations;
  }, [refreshConversations]);

  // Separate function for initial load to avoid circular dependency
  const initialLoadConversations = useCallback(async () => {
    try {
      const { conversations: list, total_count } = await listConversations(
        token,
        CONVERSATIONS_PAGE_SIZE,
        0,
      );
      setConversations(list);
      setConversationOffset(CONVERSATIONS_PAGE_SIZE);
      setTotalConversations(total_count);
      setHasMoreConversations(list.length < total_count);
    } catch (err) {
      console.error('Failed to list conversations:', err);
    }
  }, [token]);

  const loadMoreConversations = useCallback(async () => {
    if (!hasMoreConversations) return;
    await refreshConversations(false);
  }, [hasMoreConversations, refreshConversations]);

  // Initial load only when token changes
  useEffect(() => {
    if (token) {
      // Reset pagination and load first page
      setConversationOffset(0);
      setHasMoreConversations(true);
      initialLoadConversations();
    } else {
      setConversations([]);
      setTotalConversations(0);
    }
  }, [token, initialLoadConversations]);

  const mapHistoryToMessages = useCallback(
    (history: ConversationHistoryResponse['messages']): Message[] => {
      return history.map((msg, idx) => {
        const baseMessage: Message = {
          id: `${msg.timestamp}-${idx}`,
          role: msg.role,
          content: msg.content,
          timestamp: new Date(msg.timestamp),
          sources: msg.sources,
          intent: msg.intent,
          thinking: msg.thinking,
        };

        // Extract image URLs from sources for user messages
        if (msg.role === 'user' && msg.sources && Array.isArray(msg.sources)) {
          const imageSources = msg.sources.filter(
            (s: { type?: string }) => s.type === 'image'
          );
          if (imageSources.length > 0) {
            baseMessage.images = imageSources.map(
              (s: { url?: string; thumb_url?: string }) => s.thumb_url || s.url || ''
            ).filter(Boolean);
          }
        }

        // Restore timing information from persisted data
        // We store durations, so we need to reconstruct start/end times for display
        if (msg.thinking_duration_ms !== undefined && msg.thinking_duration_ms !== null) {
          // Use timestamp as a reference point to calculate approximate times
          const msgTime = new Date(msg.timestamp).getTime();
          const totalDuration = (msg.thinking_duration_ms || 0) + (msg.answer_duration_ms || 0);

          // Reconstruct timing based on durations
          baseMessage.thinkingStartTime = msgTime - totalDuration;
          baseMessage.thinkingEndTime = baseMessage.thinkingStartTime + msg.thinking_duration_ms;
        }

        if (msg.answer_duration_ms !== undefined && msg.answer_duration_ms !== null) {
          const msgTime = new Date(msg.timestamp).getTime();
          baseMessage.answerEndTime = msgTime;
          baseMessage.answerStartTime = msgTime - msg.answer_duration_ms;
        }

        return baseMessage;
      });
    },
    []
  );

  const sendMessage = useCallback(async (content: string, extraOptions?: ExtraOptions, images?: ImageData[]) => {
    if ((!content.trim() && (!images || images.length === 0)) || isLoading) return;
    if (!token) {
      setError('Please log in to start chatting.');
      return;
    }

    setError(null);
    setIsLoading(true);
    setIsStreaming(true);

    // Create abort controller for this specific conversation's request
    const abortController = new AbortController();

    // Add user message (include images as base64 preview URLs)
    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content: content.trim(),
      timestamp: new Date(),
      images: images?.map(img => `data:${img.mime_type};base64,${img.data}`),
    };
    
    // Create assistant message placeholder (no content until LLM starts streaming)
    const assistantMessageId = generateId();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    };

    // Track the conversation ID for this streaming session
    // If we don't have a server conversation yet, create a provisional id so switching works
    let streamingConvId = conversationId ?? `temp-${assistantMessageId}`;
    const isTempConversation = !conversationId;
    
    // Capture current messages for initial state
    const currentMessages = messages;

    // Add assistant placeholder and seed cache immediately so switching before first token is safe
    const initialMessages = [...currentMessages, userMessage, assistantMessage];
    setMessages(initialMessages);
    
    // Store in cache with abort controller
    streamingCacheRef.current.set(streamingConvId, {
      conversationId: streamingConvId,
      messages: initialMessages,
      isStreaming: true,
      tempId: isTempConversation ? streamingConvId : undefined,
      abortController,
    });
    saveStreamingCache(streamingCacheRef.current);

    // If this is a brand-new conversation, insert a provisional entry so it appears in the list
    if (isTempConversation) {
      setConversationId(streamingConvId);
      setConversations(prev => {
        // Avoid duplicates
        if (prev.find(c => c.id === streamingConvId)) return prev;
        return [
          {
            id: streamingConvId,
            title: 'New Conversation',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            message_count: 0,
            last_message_preview: content.slice(0, 50),
          },
          ...prev,
        ];
      });
    }

    // Helper to update cache and optionally UI
    const updateStreamingState = (
      updater: (messages: Message[]) => Message[],
      streaming: boolean
    ) => {
      const cached = streamingCacheRef.current.get(streamingConvId);
      if (!cached) return;
      
      const updatedMessages = updater(cached.messages);
      const updatedState: StreamingState = {
        ...cached,
        messages: updatedMessages,
        isStreaming: streaming,
      };
      streamingCacheRef.current.set(streamingConvId, updatedState);
      saveStreamingCache(streamingCacheRef.current);
      
      // Only update UI if this conversation is currently displayed
      if (currentConversationIdRef.current === streamingConvId) {
        setMessagesRef.current(updatedMessages);
        setIsStreamingRef.current(streaming);
      }
    };

    try {
      let currentContent = '';
      let currentIntent: IntentInfo | undefined;
      let currentVision: VisionInfo | undefined;
      let currentSources: Source[] = [];
      let currentThinking: string[] = [];
      
      // Timing tracking
      let thinkingStartTime: number | undefined;
      let thinkingEndTime: number | undefined;
      let answerStartTime: number | undefined;

      for await (const event of streamConversation({
        message: content,
        conversation_id: conversationId,
        extra_options: extraOptions,
        images: images,
      }, token, abortController.signal)) {
        // Check if aborted
        if (abortController.signal.aborted) {
          break;
        }

        switch (event.type) {
          case 'vision':
            currentVision = event.data as VisionInfo;
            updateStreamingState(
              msgs => msgs.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, vision: currentVision }
                  : msg
              ),
              true
            );
            break;

          case 'intent':
            currentIntent = event.data as IntentInfo;
            updateStreamingState(
              msgs => msgs.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, intent: currentIntent }
                  : msg
              ),
              true
            );
            break;

          case 'thinking':
            {
              const thought = event.content || (typeof event.data === 'string' ? event.data : '');
              if (thought) {
                // Record thinking start time on first thinking event
                if (!thinkingStartTime) {
                  thinkingStartTime = Date.now();
                }
                currentThinking = [...currentThinking, thought];
                updateStreamingState(
                  msgs => msgs.map(msg =>
                    msg.id === assistantMessageId
                      ? { ...msg, thinking: currentThinking, thinkingStartTime }
                      : msg
                  ),
                  true
                );
              }
            }
            break;

          case 'text':
            // Record thinking end time and answer start time on first text event
            if (!answerStartTime) {
              answerStartTime = Date.now();
              if (thinkingStartTime && !thinkingEndTime) {
                thinkingEndTime = answerStartTime;
              }
            }
            currentContent += event.content || '';
            updateStreamingState(
              msgs => msgs.map(msg =>
                msg.id === assistantMessageId
                  ? { 
                      ...msg, 
                      content: currentContent,
                      thinkingStartTime,
                      thinkingEndTime,
                      answerStartTime,
                    }
                  : msg
              ),
              true
            );
            break;

          case 'sources':
            currentSources = event.data as Source[];
            updateStreamingState(
              msgs => msgs.map(msg =>
                msg.id === assistantMessageId
                  ? { ...msg, sources: currentSources }
                  : msg
              ),
              true
            );
            break;

          case 'done':
            {
              // Record answer end time
              const answerEndTime = Date.now();
              
              if (event.conversation_id) {
                const newId = event.conversation_id;
                // Move cache entry from temp to real id
                if (isTempConversation && streamingConvId !== newId) {
                  const cached = streamingCacheRef.current.get(streamingConvId);
                  if (cached) {
                    streamingCacheRef.current.delete(streamingConvId);
                    streamingCacheRef.current.set(newId, { ...cached, conversationId: newId, tempId: streamingConvId });
                  }
                  // Replace provisional conversation list entry
                  setConversationsRef.current(prev =>
                    prev.map(c => (c.id === streamingConvId ? { ...c, id: newId } : c))
                  );
                  
                  // Update current conversation ID if still viewing this conversation
                  if (currentConversationIdRef.current === streamingConvId) {
                    setConversationIdRef.current(newId);
                    // Also update the ref directly to ensure sync check works
                    currentConversationIdRef.current = newId;
                  }
                }
                streamingConvId = newId;
                refreshConversationsRef.current?.(true);
              }
              
              // IMPORTANT: Update UI state BEFORE clearing cache
              // Get final messages with timing data
              const cached = streamingCacheRef.current.get(streamingConvId);
              const finalMessages = cached 
                ? cached.messages.map(msg =>
                    msg.id === assistantMessageId
                      ? { 
                          ...msg, 
                          isStreaming: false,
                          thinkingStartTime,
                          thinkingEndTime,
                          answerStartTime,
                          answerEndTime,
                        }
                      : msg
                  )
                : [];
              
              // Update UI directly if this conversation is currently displayed
              if (currentConversationIdRef.current === streamingConvId && finalMessages.length > 0) {
                setMessagesRef.current(finalMessages);
                setIsStreamingRef.current(false);
              }

              // Now clear cache after UI is updated
              streamingCacheRef.current.delete(streamingConvId);
              clearStreamingCache(streamingConvId);
            }
            break;
        }

        await waitForNextTick();
      }

      // Mark streaming as complete even if loop finished without 'done' event
      const finalEndTime = Date.now();
      updateStreamingState(
        msgs => msgs.map(msg =>
          msg.id === assistantMessageId
            ? { 
                ...msg, 
                isStreaming: false,
                thinkingStartTime,
                thinkingEndTime: thinkingEndTime || (answerStartTime ? answerStartTime : undefined),
                answerStartTime,
                answerEndTime: finalEndTime,
              }
            : msg
        ),
        false
      );
      
      // Clear cache when streaming is done
      streamingCacheRef.current.delete(streamingConvId);
      clearStreamingCache(streamingConvId);
      
    } catch (err) {
      // Don't show error if it was an abort (user explicitly stopped)
      if (err instanceof Error && err.name === 'AbortError') {
        // User explicitly stopped generation - update UI to show stopped state
        updateStreamingState(
          msgs => msgs.map(msg =>
            msg.id === assistantMessageId
              ? { ...msg, isStreaming: false, content: msg.content || '(Generation stopped)' }
              : msg
          ),
          false
        );
        // Clear cache since user stopped it explicitly
        streamingCacheRef.current.delete(streamingConvId);
        clearStreamingCache(streamingConvId);
       } else {
         console.error('Failed to send message:', err);
         
         // Stop streaming on error
         updateStreamingState(
           msgs => msgs.map(msg =>
             msg.id === assistantMessageId
               ? { ...msg, isStreaming: false }
               : msg
           ),
           false
         );
         
         // Only show error if this conversation is currently displayed
         if (currentConversationIdRef.current === streamingConvId) {
           setError(err instanceof Error ? err.message : 'Failed to send message');
           // Remove the failed assistant message
           setMessages(prev => prev.filter(msg => msg.id !== assistantMessageId));
         }
         
         // Clear cache on real error
         streamingCacheRef.current.delete(streamingConvId);
         clearStreamingCache(streamingConvId);
         
         // Also remove temp conversation from list
         if (isTempConversation) {
           setConversationsRef.current(prev => prev.filter(c => c.id !== streamingConvId));
         }
       }
    } finally {
      // Only update loading state if this conversation is still displayed
      if (currentConversationIdRef.current === streamingConvId) {
        setIsLoading(false);
        setIsStreaming(false);
      }
    }
  }, [conversationId, isLoading, token, messages]);
  
  const selectConversation = useCallback(async (id: string) => {
    if (!id) return;

    // Don't abort ongoing requests - let them continue in background
    // Just switch the view

    // Check if we have cached streaming state for this conversation
    const cachedState = streamingCacheRef.current.get(id);
    if (cachedState && cachedState.isStreaming) {
      // Only restore from cache if streaming is STILL IN PROGRESS
      // If isStreaming is false, it means the connection was lost (e.g., page refresh)
      // and we should load fresh data from server instead of using stale cache
      setConversationId(cachedState.conversationId);
      setMessages(cachedState.messages);
      setIsStreaming(cachedState.isStreaming);
      setIsLoading(cachedState.isStreaming); // Show loading if still streaming
      setError(null);
      return;
    }

    // Clear any stale cache for this conversation (isStreaming=false means connection was lost)
    if (cachedState && !cachedState.isStreaming) {
      streamingCacheRef.current.delete(id);
      clearStreamingCache(id);
    }

    // Check if this is a temporary ID (not yet created on server)
    // These IDs start with 'temp-'
    if (id.startsWith('temp-')) {
      // This is a temp conversation that hasn't been saved yet
      // Just clear the view - the conversation doesn't exist on server
      setConversationId(undefined);
      setMessages([]);
      setError('This conversation has not been saved yet.');
      return;
    }

    // Reset streaming state when switching to a non-cached conversation
    setIsStreaming(false);
    setIsLoading(true);
    setError(null);
    try {
      const history = await getConversationHistory(id, token);
      setConversationId(history.conversation_id);
      setMessages(mapHistoryToMessages(history.messages));
    } catch (err) {
      console.error('Failed to load conversation:', err);
      setError(err instanceof Error ? err.message : 'Failed to load conversation');
    } finally {
      setIsLoading(false);
    }
  }, [mapHistoryToMessages, token]);

  const clearMessages = useCallback(() => {
    // When starting a new chat, don't abort ongoing requests for other conversations
    // Just clear the current view
    setMessages([]);
    setConversationId(undefined);
    setError(null);
    setIsStreaming(false);
    setIsLoading(false);
  }, []);

  const removeConversation = useCallback(async (id: string) => {
    if (!id || !token) return false;
    
    // Handle temp conversations (not yet saved to server)
    if (id.startsWith('temp-')) {
      // Abort if streaming
      const cached = streamingCacheRef.current.get(id);
      if (cached?.abortController) {
        cached.abortController.abort();
      }
      // Remove from local state
      streamingCacheRef.current.delete(id);
      clearStreamingCache(id);
      setConversations(prev => prev.filter(c => c.id !== id));
      if (conversationId === id) {
        setMessages([]);
        setConversationId(undefined);
      }
      return true;
    }
    
    try {
      // Abort if streaming
      const cached = streamingCacheRef.current.get(id);
      if (cached?.abortController) {
        cached.abortController.abort();
      }
      
      await deleteConversation(id, token);
      // Clear cache for this conversation
      streamingCacheRef.current.delete(id);
      clearStreamingCache(id);
      // Refresh the entire conversation list from server
      await initialLoadConversations();
      // If we're viewing the deleted conversation, clear it
      if (conversationId === id) {
        setMessages([]);
        setConversationId(undefined);
      }
      return true;
    } catch (err) {
      console.error('Failed to delete conversation:', err);
      setError(err instanceof Error ? err.message : 'Failed to delete conversation');
      return false;
    }
  }, [conversationId, token, initialLoadConversations]);

  const renameConversation = useCallback(async (id: string, newTitle: string) => {
    if (!id || !token) return false;
    try {
      await updateConversationTitle(id, newTitle, token);
      // Update local state
      setConversations(prev =>
        prev.map(conv =>
          conv.id === id ? { ...conv, title: newTitle } : conv
        )
      );
      return true;
    } catch (err) {
      console.error('Failed to rename conversation:', err);
      setError(err instanceof Error ? err.message : 'Failed to rename conversation');
      return false;
    }
  }, [token]);

  const stopGeneration = useCallback(() => {
    // Stop the current conversation's streaming
    if (conversationId) {
      const cached = streamingCacheRef.current.get(conversationId);
      if (cached?.abortController) {
        cached.abortController.abort();
      }
    }
    
    setIsLoading(false);
    setIsStreaming(false);
    
    // Mark any streaming messages as complete
    setMessages(prev =>
      prev.map(msg =>
        msg.isStreaming ? { ...msg, isStreaming: false } : msg
      )
    );
  }, [conversationId]);

  return {
    messages,
    conversationId,
    conversations,
    totalConversations,
    hasMoreConversations,
    isLoading,
    isStreaming,
    error,
    sendMessage,
    selectConversation,
    refreshConversations,
    loadMoreConversations,
    clearMessages,
    stopGeneration,
    removeConversation,
    renameConversation,
  };
}
