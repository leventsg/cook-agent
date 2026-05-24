/**
 * Conversation Context
 * Provides conversation state and methods throughout the app
 * This ensures consistent state between components that need access to conversation data
 */

import { createContext, useContext, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useConversation } from '../hooks';
import { useAuth } from './AuthContext';

// Re-export the return type of useConversation for the context value
export type ConversationContextValue = ReturnType<typeof useConversation>;

const ConversationContext = createContext<ConversationContextValue | undefined>(undefined);

export function ConversationProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const conversationState = useConversation(token || undefined);

  // Memoize the context value to prevent unnecessary re-renders
  const value = useMemo(() => conversationState, [conversationState]);

  return (
    <ConversationContext.Provider value={value}>
      {children}
    </ConversationContext.Provider>
  );
}

/**
 * Hook to access conversation context
 */
export function useConversationContext(): ConversationContextValue {
  const ctx = useContext(ConversationContext);
  if (!ctx) {
    throw new Error('useConversationContext must be used within ConversationProvider');
  }
  return ctx;
}
