
import { createContext, useContext, useMemo } from 'react';
import type { ReactNode } from 'react';
import { useAgent } from '../hooks/useAgent';
import { useAuth } from './AuthContext';

export type AgentContextValue = ReturnType<typeof useAgent>;

const AgentContext = createContext<AgentContextValue | undefined>(undefined);

export function AgentProvider({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const agentState = useAgent(token || undefined);

  const value = useMemo(() => agentState, [agentState]);

  return (
    <AgentContext.Provider value={value}>
      {children}
    </AgentContext.Provider>
  );
}

export function useAgentContext(): AgentContextValue {
  const ctx = useContext(AgentContext);
  if (!ctx) {
    throw new Error('useAgentContext must be used within AgentProvider');
  }
  return ctx;
}
