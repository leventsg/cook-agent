/**
 * Thinking Block Component
 * Displays the AI thinking process with expandable steps
 */

import { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Loader2, CheckCircle2 } from 'lucide-react';

export interface ThinkingBlockProps {
  steps: string[];
  isThinking: boolean;
  thinkingDuration?: number; // Duration in milliseconds
  hasError?: boolean; // Whether an error occurred during thinking
}

export function ThinkingBlock({ steps, isThinking, thinkingDuration, hasError = false }: ThinkingBlockProps) {
  const [isOpen, setIsOpen] = useState(true);
  const hasSteps = steps.length > 0;
  const shouldRender = hasSteps || isThinking;

  // Auto-collapse when thinking is done
  useEffect(() => {
    if (!isThinking) {
      setIsOpen(false);
    } else {
      setIsOpen(true);
    }
  }, [isThinking]);

  if (!shouldRender) return null;

  // Format duration for display
  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  return (
    <div className="my-2 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-gray-50 dark:bg-gray-800/50">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-2 text-sm text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
        aria-expanded={isOpen}
        aria-controls="thinking-steps"
      >
        <div className="flex items-center gap-2">
          {isThinking ? (
            <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
          ) : (
            <CheckCircle2 className="w-4 h-4 text-green-500" />
          )}
          <span className="font-medium">Thinking Process</span>
          {!isThinking && thinkingDuration !== undefined && !hasError && (
            <span className="text-xs text-gray-400 dark:text-gray-500">
              ({formatDuration(thinkingDuration)})
            </span>
          )}
        </div>
        {isOpen ? (
          <ChevronDown className="w-4 h-4" />
        ) : (
          <ChevronRight className="w-4 h-4" />
        )}
      </button>
      
      {isOpen && steps.length > 0 && (
        <div
          id="thinking-steps"
          className="p-3 text-sm text-gray-600 dark:text-gray-300 space-y-1 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900/50"
        >
          {steps.map((step, index) => (
            <div
              key={`${step}-${index}`}
              className="flex items-start gap-2 animate-in fade-in slide-in-from-left-1 duration-300"
            >
              <span className="text-gray-400 mt-0.5" aria-hidden="true">•</span>
              <span>{step}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
