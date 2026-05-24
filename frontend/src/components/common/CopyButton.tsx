/**
 * Copy Button Component
 * A button that copies content to clipboard with visual feedback
 */

import { useState, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';

export interface CopyButtonProps {
  content: string;
  className?: string;
  size?: 'sm' | 'md';
}

export function CopyButton({ content, className = '', size = 'sm' }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
    }
  }, [content]);

  const iconSize = size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4';
  const buttonPadding = size === 'sm' ? 'p-1' : 'p-1.5';

  return (
    <button
      onClick={handleCopy}
      className={`
        inline-flex items-center justify-center
        ${buttonPadding} rounded-md
        text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300
        hover:bg-gray-100 dark:hover:bg-gray-800
        transition-all duration-200
        ${copied ? 'text-green-500 dark:text-green-400' : ''}
        ${className}
      `}
      title={copied ? '已复制' : '复制'}
      aria-label={copied ? 'Copied' : 'Copy to clipboard'}
    >
      {copied ? (
        <Check className={iconSize} />
      ) : (
        <Copy className={iconSize} />
      )}
    </button>
  );
}
