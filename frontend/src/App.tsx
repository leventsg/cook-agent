// src/App.tsx
import { useEffect, useState, useCallback, useRef } from 'react';
import type { ReactElement } from 'react';
import { BarChart3, BookOpen, Menu, LogOut, Utensils, ChevronDown } from 'lucide-react';
import { Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ChatWindow, ChatInput, Sidebar, KnowledgePanel } from './components';
import { AgentChatWindow, AgentChatInput } from './components/agent';
import { useTheme, useAuth, useConversationContext, useAgentContext } from './contexts';
import LoginPage from './pages/Login';
import RegisterPage from './pages/Register';
import EvaluationPage from './pages/Evaluation';
import LLMStatsPage from './pages/LLMStats';
import DietManagementPage from './pages/diet/DietManagement';

/**
 * Chat view component - handles both new chat and existing conversation
 */
function ChatView() {
  const { id: urlConversationId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { token } = useAuth();
  const isAgentMode = location.pathname.startsWith('/agent');

  // Standard Chat Context
  const {
    messages: chatMessages,
    conversationId: chatConversationId,
    isLoading: chatIsLoading,
    isStreaming: chatIsStreaming,
    error: chatError,
    sendMessage: chatSendMessage,
    selectConversation: chatSelectConversation,
    stopGeneration: chatStopGeneration,
  } = useConversationContext();

  // Agent Chat Context
  const {
      messages: agentMessages,
      sessionId: agentSessionId,
      isLoading: agentIsLoading,
      isStreaming: agentIsStreaming,
      error: agentError,
      sendMessage: agentSendMessage,
      selectSession: agentSelectSession,
      stopGeneration: agentStopGeneration,
  } = useAgentContext();

  // Unified State based on Mode
  const messages = isAgentMode ? agentMessages : chatMessages;
  const currentId = isAgentMode ? agentSessionId : chatConversationId;
  const isLoading = isAgentMode ? agentIsLoading : chatIsLoading;
  const isStreaming = isAgentMode ? agentIsStreaming : chatIsStreaming;
  const error = isAgentMode ? agentError : chatError;
  const stopGeneration = isAgentMode ? agentStopGeneration : chatStopGeneration;

  const [suggestionText, setSuggestionText] = useState<string>('');
  const [isToolSelectorOpen, setIsToolSelectorOpen] = useState(false);
  
  // Track if we've done initial sync to avoid re-triggering on subsequent renders
  const initialSyncDone = useRef(false);

  // Sync URL conversation ID with hook state on mount or when URL changes
  useEffect(() => {
    // Only sync from URL to state, not the other way around
    if (urlConversationId && urlConversationId !== currentId) {
        if (isAgentMode) {
            agentSelectSession(urlConversationId);
        } else {
            chatSelectConversation(urlConversationId);
        }
    }
    initialSyncDone.current = true;
  }, [urlConversationId, isAgentMode]); // Only depend on URL changes

  // Update URL when a NEW conversation is created (temp -> real ID)
  useEffect(() => {
    if (
      initialSyncDone.current &&
      currentId &&
      !currentId.startsWith('temp-') &&
      !urlConversationId // Only update URL if we're on /chat (no ID in URL yet)
    ) {
        const basePath = isAgentMode ? '/agent' : '/chat';
        navigate(`${basePath}/${currentId}`, { replace: true });
    }
  }, [currentId, urlConversationId, navigate, isAgentMode]);

  const handleSuggestionClick = (text: string) => {
    setSuggestionText(text);
  };

  const handleSuggestionConsumed = () => {
    setSuggestionText('');
  };

  useEffect(() => {
    if (!isAgentMode) {
      setIsToolSelectorOpen(false);
    }
  }, [isAgentMode]);

  return (
    <>
      {error && (
        <div className="absolute top-4 left-4 right-4 z-10 p-3 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg text-red-600 dark:text-red-400 text-sm">
          {error}
        </div>
      )}
      
      {isAgentMode ? (
        <>
           <AgentChatWindow 
             messages={messages} 
             isLoading={isLoading} 
             onSuggestionClick={handleSuggestionClick} 
             error={error}
             isToolSelectorOpen={isToolSelectorOpen}
           />
          <div className="p-4 max-w-4xl w-full mx-auto">
            <AgentChatInput
              onSend={agentSendMessage}
              onCancel={stopGeneration}
              disabled={isLoading}
              isStreaming={isStreaming}
              placeholder="Ask Agent to calculate, analyze, or plan..."
              externalValue={suggestionText}
              onExternalValueConsumed={handleSuggestionConsumed}
              token={token || undefined}
              onToolsOpenChange={setIsToolSelectorOpen}
            />
            <div className="text-center text-xs text-gray-400 mt-2">
              CookHero Agent can make mistakes. Consider checking important information.
            </div>
          </div>
        </>
      ) : (
        <>
           <ChatWindow 
             messages={messages} 
             isLoading={isLoading} 
             onSuggestionClick={handleSuggestionClick}
             error={error}
           />
          <div className="p-4 max-w-4xl w-full mx-auto">
            <ChatInput
              onSend={chatSendMessage}
              onCancel={stopGeneration}
              disabled={isLoading}
              isStreaming={isStreaming}
              placeholder="Ask CookHero anything about cooking..."
              externalValue={suggestionText}
              onExternalValueConsumed={handleSuggestionConsumed}
            />
            <div className="text-center text-xs text-gray-400 mt-2">
              CookHero can make mistakes. Consider checking important information.
            </div>
          </div>
        </>
      )}
    </>
  );
}

/**
 * Main layout component with sidebar
 */
function MainLayout({ children }: { children: React.ReactNode }) {
  const { username, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const isAgentMode = location.pathname.startsWith('/agent');

  // Standard Chat Context
  const {
    conversationId: chatConversationId,
    conversations: chatConversations,
    totalConversations: chatTotalConversations,
    hasMoreConversations: chatHasMoreConversations,
    selectConversation: chatSelectConversation,
    clearMessages: chatClearMessages,
    removeConversation: chatRemoveConversation,
    renameConversation: chatRenameConversation,
    loadMoreConversations: chatLoadMoreConversations,
  } = useConversationContext();

  // Agent Chat Context
  const {
      sessionId: agentSessionId,
      sessions: agentSessions,
      totalSessions: agentTotalSessions,
      hasMoreSessions: agentHasMoreSessions,
      selectSession: agentSelectSession,
      clearMessages: agentClearMessages,
      removeSession: agentRemoveSession,
      loadMoreSessions: agentLoadMoreSessions,
      renameSession: agentRenameSession,
  } = useAgentContext();

  // Unified State based on Mode
  const conversationId = isAgentMode ? agentSessionId : chatConversationId;
  // Map Agent sessions to ConversationSummary format for Sidebar
  const conversations = isAgentMode
    ? agentSessions.map(s => ({
        id: s.id,
        title: s.title ?? undefined,
        created_at: s.created_at,
        updated_at: s.updated_at,
        message_count: s.message_count,
        last_message_preview: s.last_message_preview
    }))
    : chatConversations;

  const totalConversations = isAgentMode ? agentTotalSessions : chatTotalConversations;
  const hasMoreConversations = isAgentMode ? agentHasMoreSessions : chatHasMoreConversations;
  const loadMoreConversations = isAgentMode ? agentLoadMoreSessions : chatLoadMoreConversations;
  
  const selectConversation = isAgentMode ? agentSelectSession : chatSelectConversation;
  const clearMessages = isAgentMode ? agentClearMessages : chatClearMessages;
  const removeConversation = isAgentMode ? agentRemoveSession : chatRemoveConversation;
  // Now Agent sessions support renaming
  const renameConversation = isAgentMode ? agentRenameSession : chatRenameConversation; 

  const { isDark, toggleTheme } = useTheme();
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isAnalyticsMenuOpen, setIsAnalyticsMenuOpen] = useState(false);
  const analyticsMenuRef = useRef<HTMLDivElement>(null);

  // Determine current view from pathname
  const isKnowledgeView = location.pathname.includes('/knowledge');
  const isEvaluationView = location.pathname.includes('/evaluation');
  const isLLMStatsView = location.pathname.includes('/llm-stats');
  const isDietView = location.pathname.includes('/diet');
  const isAnalyticsView = isEvaluationView || isLLMStatsView;
  const analyticsLabel = isEvaluationView ? '评估监控' : isLLMStatsView ? '模型统计' : '数据分析';

  useEffect(() => {
    setIsAnalyticsMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (analyticsMenuRef.current && !analyticsMenuRef.current.contains(event.target as Node)) {
        setIsAnalyticsMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const goBackToChat = useCallback(() => {
    const basePath = isAgentMode ? '/agent' : '/chat';
    if (conversationId && !conversationId.startsWith('temp-')) {
      navigate(`${basePath}/${conversationId}`);
    } else {
      navigate(basePath);
    }
  }, [conversationId, isAgentMode, navigate]);

  const handleToggleAgentMode = useCallback(() => {
      if (isAgentMode) {
          navigate('/chat');
      } else {
          navigate('/agent');
      }
  }, [isAgentMode, navigate]);

  const handleNewChat = useCallback(() => {
    clearMessages();
    navigate(isAgentMode ? '/agent' : '/chat');
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  }, [clearMessages, navigate, isAgentMode]);

  const handleSelectConversation = useCallback((id: string) => {
    selectConversation(id);
    const basePath = isAgentMode ? '/agent' : '/chat';
    navigate(`${basePath}/${id}`);
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  }, [selectConversation, navigate, isAgentMode]);

  const handleLogout = useCallback(() => {
    logout();
    navigate('/login');
  }, [logout, navigate]);

  return (
    <div className="flex h-screen bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 transition-colors duration-200">
      <Sidebar
        isOpen={isSidebarOpen}
        toggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        conversations={conversations}
        totalConversations={totalConversations}
        hasMoreConversations={hasMoreConversations}
        onLoadMoreConversations={loadMoreConversations}
        currentConversationId={conversationId || null}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteConversation={removeConversation}
        onRenameConversation={renameConversation}
        isDark={isDark}
        toggleTheme={toggleTheme}
        isAgentMode={isAgentMode}
        onToggleAgentMode={handleToggleAgentMode}
      />

      <div className="flex-1 flex flex-col h-full relative">
        <header className="h-14 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm flex items-center px-4 justify-between z-50">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="p-2 -ml-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
              title={isSidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
            >
              <Menu className="w-5 h-5" />
            </button>
            {/* <div className="flex items-center gap-2">
              <span className="text-2xl">🍳</span>
              <h1 className="font-bold text-gray-800 dark:text-gray-100">CookHero</h1>
            </div> */}
          </div>
          <div className="flex items-center gap-1.5 sm:gap-3 text-xs text-gray-600 dark:text-gray-300 overflow-visible">
            {!isKnowledgeView && !isEvaluationView && !isLLMStatsView && !isDietView && conversationId && (
              <span className="hidden sm:inline font-mono bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded truncate" title={conversationId}>
                ID: {conversationId}
              </span>
            )}
            <button
              onClick={() => {
                if (isDietView) {
                  const basePath = isAgentMode ? '/agent' : '/chat';
                  if (conversationId && !conversationId.startsWith('temp-')) {
                    navigate(`${basePath}/${conversationId}`);
                  } else {
                    navigate(basePath);
                  }
                } else {
                  navigate(isAgentMode ? '/agent/diet' : '/diet');
                }
              }}
              className={`flex items-center gap-1 px-2 sm:px-3 py-1 rounded-full border transition-colors shrink-0 ${
                isDietView
                  ? 'border-green-400 bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-200 dark:border-green-600'
                  : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              <Utensils className="w-4 h-4" />
              <span className="hidden sm:inline">{isDietView ? '返回对话' : '饮食管理'}</span>
            </button>
            <button
              onClick={() => {
                if (isKnowledgeView) {
                  const basePath = isAgentMode ? '/agent' : '/chat';
                  if (conversationId && !conversationId.startsWith('temp-')) {
                    navigate(`${basePath}/${conversationId}`);
                  } else {
                    navigate(basePath);
                  }
                } else {
                  navigate(isAgentMode ? '/agent/knowledge' : '/knowledge');
                }
              }}
              className={`flex items-center gap-1 px-2 sm:px-3 py-1 rounded-full border transition-colors shrink-0 ${
                isKnowledgeView
                  ? 'border-blue-400 bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-200 dark:border-blue-600'
                  : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800'
              }`}
            >
              <BookOpen className="w-4 h-4" />
              <span className="hidden sm:inline">{isKnowledgeView ? '返回对话' : '知识库'}</span>
            </button>
            <div ref={analyticsMenuRef} className="relative">
              <button
                onClick={() => setIsAnalyticsMenuOpen(prev => !prev)}
                className={`flex items-center gap-1 px-2 sm:px-3 py-1 rounded-full border transition-all duration-200 shrink-0 ${
                  isAnalyticsView
                    ? 'border-orange-400 bg-orange-50 text-orange-700 dark:bg-orange-900/30 dark:text-orange-200 dark:border-orange-600'
                    : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200 hover:bg-orange-50 dark:hover:bg-orange-900/20 hover:border-orange-300 dark:hover:border-orange-700'
                }`}
              >
                <BarChart3 className="w-4 h-4" />
                <span className="hidden sm:inline">{analyticsLabel}</span>
                <ChevronDown className="w-4 h-4" />
              </button>
              {isAnalyticsMenuOpen && (
                <div className="absolute right-0 mt-2 rounded-xl border border-gray-200/60 dark:border-gray-700/60 bg-white/95 dark:bg-gray-900/95 backdrop-blur-sm shadow-xl overflow-hidden z-50">
                  {isAnalyticsView && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setIsAnalyticsMenuOpen(false);
                        goBackToChat();
                      }}
                      className="w-full text-left px-4 py-2.5 text-sm text-gray-600 dark:text-gray-300 hover:bg-gradient-to-r hover:from-orange-50 hover:to-orange-100/50 dark:hover:from-orange-900/30 dark:hover:to-orange-900/10 border-b border-gray-100/50 dark:border-gray-800/50 transition-all duration-200 flex items-center gap-2"
                    >
                      {/* <span className="text-orange-500">←</span> */}
                      返回对话
                    </button>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsAnalyticsMenuOpen(false);
                      navigate(isAgentMode ? '/agent/evaluation' : '/evaluation');
                    }}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-all duration-200 flex items-center gap-2.5 ${
                      isEvaluationView
                        ? 'text-orange-600 dark:text-orange-400 bg-gradient-to-r from-orange-50 to-orange-100/50 dark:from-orange-900/30 dark:to-orange-900/20 font-medium'
                        : 'text-gray-700 dark:text-gray-200 hover:bg-gradient-to-r hover:from-orange-50 hover:to-orange-100/50 dark:hover:from-orange-900/30 dark:hover:to-orange-900/10'
                    }`}
                  >
                                       评估监控
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsAnalyticsMenuOpen(false);
                      navigate(isAgentMode ? '/agent/llm-stats' : '/llm-stats');
                    }}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-all duration-200 flex items-center gap-2.5 ${
                      isLLMStatsView
                        ? 'text-orange-600 dark:text-orange-400 bg-gradient-to-r from-orange-50 to-orange-100/50 dark:from-orange-900/30 dark:to-orange-900/20 font-medium'
                        : 'text-gray-700 dark:text-gray-200 hover:bg-gradient-to-r hover:from-orange-50 hover:to-orange-100/50 dark:hover:from-orange-900/30 dark:hover:to-orange-900/10'
                    }`}
                  >
                     模型统计
                  </button>
                </div>
              )}
            </div>
            {username && (
              <div className="flex items-center gap-1 sm:gap-2 bg-gray-100 dark:bg-gray-800 px-2 sm:px-3 py-1 rounded-full shrink-0">
                <span className="font-semibold hidden sm:inline">{username}</span>
                <button
                  onClick={handleLogout}
                  className="text-gray-500 hover:text-gray-800 dark:hover:text-gray-100 flex items-center gap-1"
                  title="Log out"
                >
                  <LogOut className="w-4 h-4" />
                  <span className="hidden md:inline">Logout</span>
                </button>
              </div>
            )}
          </div>
        </header>

        <main className="flex-1 flex flex-col overflow-hidden relative bg-gradient-to-b from-white to-gray-50 dark:from-gray-900 dark:to-gray-950">
          {children}
        </main>
      </div>
    </div>
  );
}

function RequireAuth({ children }: { children: ReactElement }) {
  const { isAuthenticated, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // Listen for auth-unauthorized event (triggered when 401 response received)
  useEffect(() => {
    const handleUnauthorized = () => {
      logout();
      navigate('/login', { replace: true });
    };

    window.addEventListener('auth-unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth-unauthorized', handleUnauthorized);
  }, [logout, navigate]);

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

function App() {
  return (
    <Routes>
      {/* Protected routes with main layout */}
      <Route
        path="/chat"
        element={
          <RequireAuth>
            <MainLayout>
              <ChatView />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/chat/:id"
        element={
          <RequireAuth>
            <MainLayout>
              <ChatView />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/knowledge"
        element={
          <RequireAuth>
            <MainLayout>
              <KnowledgePanel />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/knowledge"
        element={
          <RequireAuth>
            <MainLayout>
              <KnowledgePanel />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/evaluation"
        element={
          <RequireAuth>
            <MainLayout>
              <EvaluationPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/evaluation"
        element={
          <RequireAuth>
            <MainLayout>
              <EvaluationPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/llm-stats"
        element={
          <RequireAuth>
            <MainLayout>
              <LLMStatsPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/llm-stats"
        element={
          <RequireAuth>
            <MainLayout>
              <LLMStatsPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/diet"
        element={
          <RequireAuth>
            <MainLayout>
              <DietManagementPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/diet"
        element={
          <RequireAuth>
            <MainLayout>
              <DietManagementPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent"
        element={
          <RequireAuth>
            <MainLayout>
              <ChatView />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/:id"
        element={
          <RequireAuth>
            <MainLayout>
              <ChatView />
            </MainLayout>
          </RequireAuth>
        }
      />
      {/* Auth routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      {/* Default redirect to agent */}
      <Route path="/" element={<Navigate to="/agent" replace />} />
      <Route path="*" element={<Navigate to="/agent" replace />} />
    </Routes>
  );
}

export default App;
