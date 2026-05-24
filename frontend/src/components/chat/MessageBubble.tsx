/**
 * Message Bubble Component
 * Displays individual chat messages with styling based on role
 */

import { useState, useEffect } from 'react';
import { Search, MessageCircle, Globe, BookOpen, ExternalLink, Clock, Loader2 } from 'lucide-react';
import type { Message, Source } from '../../types';
import { INTENT_LABELS } from '../../constants';
import { MarkdownRenderer } from './MarkdownRenderer';
import { ThinkingBlock } from './ThinkingBlock';
import { CopyButton } from '../common';

export interface MessageBubbleProps {
  message: Message;
  hasError?: boolean;
}

/**
 * Extract intent string from message.intent
 */
function extractIntent(intent: Message['intent']): string | undefined {
  if (!intent) return undefined;
  if (typeof intent === 'string') return intent;
  if (typeof intent === 'object' && 'intent' in intent) {
    return (intent as { intent: string }).intent;
  }
  return undefined;
}

/**
 * Get source display configuration based on type
 */
function getSourceStyle(type: string): {
  icon: typeof BookOpen;
  dotColor: string;
  label: string;
} {
  if (type === 'web') {
    return {
      icon: Globe,
      dotColor: 'bg-blue-400',
      label: '🌐',
    };
  }
  // Default to 'rag' / knowledge base
  return {
    icon: BookOpen,
    dotColor: 'bg-green-400',
    label: '📚',
  };
}

/**
 * Render a single source item with type-based styling
 */
function SourceItem({ source, index }: { source: Source; index: number }) {
  const style = getSourceStyle(source.type);
  const isWeb = source.type === 'web';

  const content = (
    <span className="flex items-center gap-1">
      <span>{source.info}</span>
      {isWeb && source.url && (
        <ExternalLink className="w-3 h-3 opacity-60" />
      )}
    </span>
  );

  return (
    <li
      key={index}
      className="text-xs text-gray-600 dark:text-gray-400 flex items-center gap-2"
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${style.dotColor} shrink-0`}
        aria-hidden="true"
      />
      {isWeb && source.url ? (
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-blue-500 hover:underline transition-colors"
          title={source.url}
        >
          {content}
        </a>
      ) : (
        content
      )}
    </li>
  );
}

export function MessageBubble({ message, hasError = false }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const hasText = !!(message.content && message.content.trim().length > 0);
  const thinkingSteps = message.thinking ?? [];
  const hasThinkingSteps = thinkingSteps.length > 0;
  const isThinkingPhase = !isUser && !!message.isStreaming && !hasText;
  const showThinkingBlock = !isUser && (hasThinkingSteps || isThinkingPhase);
  const rawIntent = extractIntent(message.intent);

  // Calculate durations
  const thinkingDuration = message.thinkingStartTime && message.thinkingEndTime
    ? message.thinkingEndTime - message.thinkingStartTime
    : undefined;
  const answerDuration = message.answerStartTime && message.answerEndTime
    ? message.answerEndTime - message.answerStartTime
    : undefined;
  const totalDuration = message.thinkingStartTime && message.answerEndTime
    ? message.answerEndTime - message.thinkingStartTime
    : (message.answerStartTime && message.answerEndTime 
        ? message.answerEndTime - message.answerStartTime 
        : undefined);

  // Real-time elapsed time tracking for streaming
  const [elapsedTime, setElapsedTime] = useState(0);
  const startTime = message.thinkingStartTime || message.answerStartTime;
  
  useEffect(() => {
    if (!message.isStreaming || !startTime) {
      setElapsedTime(0);
      return;
    }
    
    // Update elapsed time every 100ms
    const interval = setInterval(() => {
      setElapsedTime(Date.now() - startTime);
    }, 100);
    
    return () => clearInterval(interval);
  }, [message.isStreaming, startTime]);

  // Format duration for display
  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  return (
    <div className={`flex mb-6 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`flex flex-col w-full ${
          isUser ? 'items-end' : 'items-start'
        }`}
      >
        {/* Intent Indicator (Assistant only) */}
        <div className="flex items-center gap-2 mb-1.5">
          {!isUser && rawIntent && (
            <div className="flex items-center">
              {rawIntent === 'general_chat' ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 text-xs font-medium border border-blue-200 dark:border-blue-800">
                  <MessageCircle className="w-3 h-3" />
                  直接回复
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 text-xs font-medium border border-green-200 dark:border-green-800">
                  <Search className="w-3 h-3" />
                  {`知识库检索 · ${INTENT_LABELS[rawIntent] ?? rawIntent}`}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Thinking Block (Assistant only) */}
        {showThinkingBlock && (
          <div className="w-full mb-2">
            <ThinkingBlock 
              steps={thinkingSteps} 
              isThinking={isThinkingPhase} 
              thinkingDuration={thinkingDuration}
              hasError={hasError}
            />
          </div>
        )}

        {/* Message Text (hide while only thinking) */}
        {!isThinkingPhase && (
          <div
            className={`text-sm leading-relaxed break-words ${
              isUser
                ? 'bg-gradient-to-br from-blue-500 to-blue-500 text-white px-4 py-1 rounded-2xl shadow-sm'
                : 'prose prose-sm dark:prose-invert max-w-none text-gray-800 dark:text-gray-100 px-0 py-0'
            }`}
          >
            {/* User Images (displayed before text) */}
            {isUser && message.images && message.images.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {message.images.map((img, idx) => (
                  <img
                    key={idx}
                    src={img}
                    alt={`Uploaded image ${idx + 1}`}
                    className="max-w-[200px] max-h-[200px] rounded-lg object-cover"
                  />
                ))}
              </div>
            )}
            <MarkdownRenderer content={message.content.trim()} />
          </div>
        )}

          {/* Sources (Assistant only) - with type-based styling */}
          {!isUser && message.sources && message.sources.length > 0 && (
            <div className="mt-3 w-full">
              {/* Group sources by type */}
              {(() => {
                const ragSources = message.sources.filter(s => s.type === 'rag');
                const webSources = message.sources.filter(s => s.type === 'web');
                
                return (
                  <>
                    {ragSources.length > 0 && (
                      <div className="mb-2">
                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-1.5 font-medium">
                          📚 知识库来源：
                        </p>
                        <ul className="space-y-1">
                          {ragSources.map((source, idx) => (
                            <SourceItem key={`rag-${idx}`} source={source} index={idx} />
                          ))}
                        </ul>
                      </div>
                    )}
                    {webSources.length > 0 && (
                      <div>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mb-1.5 font-medium">
                          🌐 网络来源：
                        </p>
                        <ul className="space-y-1">
                          {webSources.map((source, idx) => (
                            <SourceItem key={`web-${idx}`} source={source} index={idx} />
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                );
              })()}
            </div>
          )}


        {/* Timestamp and Duration Stats */}
        <div
          className={`text-xs mt-2 flex items-center gap-2 flex-wrap ${
            isUser ? 'text-gray-500 dark:text-gray-400' : 'text-gray-600 dark:text-gray-400'
          }`}
        >
            {/* Copy button at the end of timestamp row */}
          {hasText && isUser && (
            <CopyButton content={message.content.trim()} size="sm" />
          )}
          <span>
            {message.timestamp.toLocaleTimeString('zh-CN', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
          
          {/* Real-time elapsed time during streaming */}
          {!isUser && message.isStreaming && elapsedTime > 0 && (
            <span className="inline-flex items-center gap-1 text-blue-500 dark:text-blue-400">
              <Loader2 className="w-3 h-3 animate-spin" />
              {formatDuration(elapsedTime)}
            </span>
          )}
          
          {/* Duration breakdown after completion */}
          {!isUser && !message.isStreaming && (thinkingDuration !== undefined || answerDuration !== undefined) && (
            <span className="inline-flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {thinkingDuration !== undefined && answerDuration !== undefined ? (
                <span>
                  思考 {formatDuration(thinkingDuration)} · 生成 {formatDuration(answerDuration)}
                </span>
              ) : totalDuration !== undefined ? (
                <span>耗时 {formatDuration(totalDuration)}</span>
              ) : null}
            </span>
          )}
          
          {/* Copy button at the end of timestamp row */}
          {hasText && !isUser && (
            <CopyButton content={message.content.trim()} size="sm" />
          )}
        </div>
      </div>
    </div>
  );
}
