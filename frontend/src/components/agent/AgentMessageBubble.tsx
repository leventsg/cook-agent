/**
 * Agent Message Bubble Component
 * Displays individual chat messages with Agent-specific styling and trace rendering
 */

import { useState, useEffect, useRef } from 'react';
import { Clock, Loader2, BookOpen, Globe, ExternalLink } from 'lucide-react';
import type { Message, Source } from '../../types';
import { MarkdownRenderer } from '../chat/MarkdownRenderer';
import { AgentThinkingBlock, type TraceStep } from './AgentThinkingBlock';
import { CopyButton } from '../common';

export interface AgentMessageBubbleProps {
  message: Message;
  hasError?: boolean;
}

/**
 * Extract image URLs from trace data for user messages
 */
function extractImagesFromTrace(trace: any[] | undefined): string[] {
  if (!trace || trace.length === 0) return [];

  const images: string[] = [];

  for (const item of trace) {
    if (typeof item === 'object' && item !== null) {
      // Check if this is an image source entry
      if (item.type === 'image' && item.display_url) {
        images.push(item.display_url);
      }
    }
  }

  return images;
}

/**
 * Parse trace data from message - handles both string[] and object[]
 */
function parseTrace(trace: any[] | undefined): TraceStep[] {
  if (!trace || trace.length === 0) return [];
  
  return trace.map((item) => {
    // If it's already an object, use it directly
    if (typeof item === 'object' && item !== null) {
      return {
        error: item.error || null,
        action: item.action || item.type || 'unknown',
        content: item.content || null,
        iteration: item.iteration ?? 0,
        timestamp: item.timestamp || new Date().toISOString(),
        tool_calls: item.tool_calls,
        source: item.source,
        subagent_name: item.subagent_name,
      };
    }
    
    // If it's a string, try to parse it as JSON
    if (typeof item === 'string') {
      try {
        const parsed = JSON.parse(item);
        return {
          error: parsed.error || null,
          action: parsed.action || parsed.type || 'unknown',
          content: parsed.content || null,
          iteration: parsed.iteration ?? 0,
          timestamp: parsed.timestamp || new Date().toISOString(),
          tool_calls: parsed.tool_calls,
          source: parsed.source,
          subagent_name: parsed.subagent_name,
        };
      } catch {
        // If parsing fails, treat as content
        return {
          error: null,
          action: 'thinking',
          content: item,
          iteration: 0,
          timestamp: new Date().toISOString(),
          tool_calls: undefined,
          source: undefined,
          subagent_name: undefined,
        };
      }
    }
    
    return {
      error: null,
      action: 'unknown',
      content: String(item),
      iteration: 0,
      timestamp: new Date().toISOString(),
      tool_calls: undefined,
      source: undefined,
      subagent_name: undefined,
    };
  });
}

function getSourceStyle(type: string): { icon: typeof BookOpen; accent: string; label: string } {
  if (type === 'web') {
    return {
      icon: Globe,
      accent: 'text-blue-500 dark:text-blue-400',
      label: 'Web Search',
    };
  }
  return {
    icon: BookOpen,
    accent: 'text-green-500 dark:text-green-400',
    label: '知识库',
  };
}

function SourceItem({ source }: { source: Source }) {
  const style = getSourceStyle(source.type);
  const Icon = style.icon;
  const isWeb = source.type === 'web';

  return (
    <li className="flex items-start gap-2 text-xs text-gray-700 dark:text-gray-300">
      <Icon className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${style.accent}`} />
      {isWeb && source.url ? (
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-blue-500 hover:underline transition-colors"
          title={source.url}
        >
          <span className="inline-flex items-center gap-1">
            {source.info}
            <ExternalLink className="w-3 h-3 opacity-60" />
          </span>
        </a>
      ) : (
        <span>{source.info}</span>
      )}
    </li>
  );
}

function buildSourcesFromTrace(trace: TraceStep[], fallbackSources?: Source[]) {
  const ragSources: Source[] = [];
  const webSources: Source[] = [];
  const seen = new Set<string>();
  let ragCount = 0;
  let webCount = 0;

  const addSource = (source: Source, target: Source[]) => {
    const key = `${source.type}:${source.info}:${source.url ?? ''}`;
    if (seen.has(key)) return;
    seen.add(key);
    target.push(source);
  };

  trace.forEach((step) => {
    if (step.action !== 'tool_result' || !step.tool_calls?.length) return;
    const toolName = step.tool_calls[0]?.name;
    const payload = step.content as Record<string, any> | null;
    if (!payload || typeof payload !== 'object') return;

    if (toolName === 'knowledge_base_search') {
      const sources = Array.isArray(payload.sources) ? payload.sources : [];
      sources.forEach((source) => {
        if (source && typeof source === 'object') {
          addSource(
            {
              type: source.type || 'rag',
              info: source.info || 'CookHero 知识库',
              url: source.url,
            },
            ragSources,
          );
        }
      });
      if (typeof payload.document_count === 'number') {
        ragCount += payload.document_count;
      } else {
        ragCount += sources.length;
      }
    }

    if (toolName === 'web_search') {
      const results = Array.isArray(payload.results) ? payload.results : [];
      results.forEach((result) => {
        if (!result || typeof result !== 'object') return;
        const info = result.title || result.content || result.url || 'Web result';
        addSource(
          {
            type: 'web',
            info: String(info).trim(),
            url: result.url,
          },
          webSources,
        );
      });
      webCount += results.length;
    }
  });

  (fallbackSources || []).forEach((source) => {
    if (!source) return;
    if (source.type === 'web') {
      addSource(source, webSources);
    } else {
      addSource(source, ragSources);
    }
  });

  if (ragCount === 0) ragCount = ragSources.length;
  if (webCount === 0) webCount = webSources.length;

  return {
    ragSources,
    webSources,
    ragCount,
    webCount,
  };
}

export function AgentMessageBubble({ message, hasError = false }: AgentMessageBubbleProps) {
  const isUser = message.role === 'user';
  const hasText = !!(message.content && message.content.trim().length > 0);

  // Parse trace data - use message.trace if available, otherwise fall back to message.thinking
  const traceData = parseTrace(message.trace || message.thinking);
  const mainTrace = traceData.filter((step) => step.source !== 'subagent');
  const subagentTrace = traceData.filter((step) => step.source === 'subagent');
  const hasTrace = mainTrace.length > 0;
  const isThinkingPhase = !isUser && !!message.isStreaming && !hasText;
  const showThinkingBlock = !isUser && (hasTrace || isThinkingPhase);
  const showSubagentBlock = !isUser && subagentTrace.length > 0;
  const lastSubagentStep = subagentTrace[subagentTrace.length - 1];
  const isSubagentThinking =
    !!message.isStreaming &&
    !!lastSubagentStep &&
    !['subagent_output', 'error'].includes(lastSubagentStep.action);
  const subagentNames = Array.from(
    new Set(subagentTrace.map((step) => step.subagent_name).filter(Boolean))
  );
  const subagentLabel = subagentNames.length === 1
    ? subagentNames[0]
    : subagentNames.length > 1
      ? `${subagentNames.length} subagents`
      : undefined;

  // Extract images from trace for user messages
  // Priority: trace URLs (after refresh) > message.images (just sent with base64)
  const tracedImages = isUser ? extractImagesFromTrace(message.trace) : [];
  const userImages = isUser
    ? (tracedImages.length > 0 ? tracedImages : message.images || [])
    : [];
  const hasUserImages = userImages.length > 0;

  // Handle both timestamp-based timing and duration-based timing
  const thinkingDuration = message.thinkingStartTime && message.thinkingEndTime
    ? message.thinkingEndTime - message.thinkingStartTime
    : (message as any).thinking_duration_ms || undefined;
  const answerDuration = message.answerStartTime && message.answerEndTime
    ? message.answerEndTime - message.answerStartTime
    : (message as any).answer_duration_ms || undefined;
  const totalDuration = message.thinkingStartTime && message.answerEndTime
    ? message.answerEndTime - message.thinkingStartTime
    : (thinkingDuration && answerDuration
        ? thinkingDuration + answerDuration
        : thinkingDuration || answerDuration || undefined);

  // Real-time elapsed time tracking for streaming
  const [elapsedTime, setElapsedTime] = useState(0);
  // Track when streaming started for this message - use useRef to persist across renders
  const streamStartTimeRef = useRef<number | undefined>(undefined);
  
  useEffect(() => {
    if (message.isStreaming) {
      // When streaming starts, record the start time if we don't have one
      if (!streamStartTimeRef.current && !message.thinkingStartTime && !message.answerStartTime) {
        streamStartTimeRef.current = Date.now();
      }
      
      const effectiveStartTime = message.thinkingStartTime || message.answerStartTime || streamStartTimeRef.current;
      if (!effectiveStartTime) return;
      
      // Update elapsed time every 100ms
      const interval = setInterval(() => {
        setElapsedTime(Date.now() - effectiveStartTime);
      }, 100);
      
      return () => clearInterval(interval);
    } else {
      // When streaming ends, reset the tracking
      streamStartTimeRef.current = undefined;
      setElapsedTime(0);
    }
  }, [message.isStreaming, message.thinkingStartTime, message.answerStartTime]);

  const { ragSources, webSources, ragCount, webCount } = buildSourcesFromTrace(
    mainTrace,
    message.sources,
  );
  const hasSources = ragSources.length > 0 || webSources.length > 0;

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
        {/* Thinking Block (Assistant only) - Show trace/execution steps */}
        {showThinkingBlock && (
          <div className="w-full mb-2">
            <AgentThinkingBlock 
              trace={mainTrace} 
              isThinking={isThinkingPhase} 
              thinkingDuration={thinkingDuration}
              hasError={hasError}
            />
          </div>
        )}
        {showSubagentBlock && (
          <div className="w-full mb-2">
            <AgentThinkingBlock
              trace={subagentTrace}
              isThinking={isSubagentThinking}
              title="Subagent Thinking"
              subtitle={subagentLabel}
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
            {isUser && hasUserImages && (
              <div className="flex flex-wrap gap-2 mb-2">
                {userImages.map((imgUrl, idx) => (
                  <img
                    key={idx}
                    src={imgUrl}
                    alt={`Uploaded image ${idx + 1}`}
                    className="max-w-[200px] max-h-[200px] rounded-lg object-cover"
                  />
                ))}
              </div>
            )}
            <MarkdownRenderer content={message.content.trim()} />
          </div>
        )}

        {/* Timestamp and Duration Stats */}
        <div
          className={`text-xs mt-2 flex items-center gap-2 flex-wrap ${
            isUser ? 'text-gray-500 dark:text-gray-400' : 'text-gray-600 dark:text-gray-400'
          }`}
        >
          {/* Copy button for user */}
          {hasText && isUser && (
            <CopyButton content={message.content.trim()} size="sm" />
          )}
          {(message.content !== '') && (
            <span>
                {message.timestamp.toLocaleTimeString('zh-CN', {
                hour: '2-digit',
                minute: '2-digit',
                })}
            </span>
        )}
          
          {/* Real-time elapsed time during streaming */}
          {!isUser && message.isStreaming && elapsedTime > 0 && (
            <span className="inline-flex items-center gap-1 text-orange-500 dark:text-orange-400">
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
          
          {!isUser && hasSources && (
            <div className="relative">
              <div className="group flex items-center gap-2 rounded-full border border-gray-200/70 dark:border-gray-700/70 bg-white/80 dark:bg-gray-900/60 px-2 py-0.5">
                {ragSources.length > 0 && (
                  <div className="relative group/knowledge flex items-center gap-1 text-[11px] text-gray-600 dark:text-gray-300">
                    <BookOpen className="w-3.5 h-3.5 text-green-500" />
                    <span>{ragCount}</span>
                    <div className="absolute left-0 top-full z-20 mt-2 hidden w-64 rounded-lg border border-gray-200/70 dark:border-gray-700/70 bg-white dark:bg-gray-900 p-3 shadow-lg group-hover/knowledge:block">
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">知识库搜索结果</p>
                      <ul className="space-y-1">
                        {ragSources.map((source, idx) => (
                          <SourceItem key={`rag-${idx}`} source={source} />
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
                {webSources.length > 0 && (
                  <div className="relative group/web flex items-center gap-1 text-[11px] text-gray-600 dark:text-gray-300">
                    <Globe className="w-3.5 h-3.5 text-blue-500" />
                    <span>{webCount}</span>
                    <div className="absolute left-0 top-full z-20 mt-2 hidden w-64 rounded-lg border border-gray-200/70 dark:border-gray-700/70 bg-white dark:bg-gray-900 p-3 shadow-lg group-hover/web:block">
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">Web Search 结果</p>
                      <ul className="space-y-1">
                        {webSources.map((source, idx) => (
                          <SourceItem key={`web-${idx}`} source={source} />
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Copy button for assistant */}
          {hasText && !isUser && (
            <CopyButton content={message.content.trim()} size="sm" />
          )}
        </div>
      </div>
    </div>
  );
}
