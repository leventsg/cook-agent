/**
 * Markdown Renderer Component
 * Renders markdown content with syntax highlighting and custom styling
 */

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import type { Components } from 'react-markdown';

// Import highlight.js styles (GitHub Dark theme)
import 'highlight.js/styles/github-dark.css';

export interface MarkdownRendererProps {
  content: string;
  className?: string;
}

// Custom components for styling
const components: Components = {
  h1: ({ children }) => (
    <h1 className="text-2xl font-bold mt-4 mb-2">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-xl font-semibold mt-4 mb-2">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-lg font-semibold mt-3 mb-2">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-base font-semibold mt-3 mb-1">{children}</h4>
  ),
  p: ({ children }) => (
    <p className="my-2 leading-relaxed">{children}</p>
  ),
  ul: ({ children }) => (
    <ul className="my-2 ml-4 list-disc space-y-1">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2 ml-4 list-decimal space-y-1">{children}</ol>
  ),
  li: ({ children }) => (
    <li className="leading-relaxed">{children}</li>
  ),
  a: ({ href, children }) => (
    <a
      href={href}
      className="text-orange-600 dark:text-orange-400 hover:underline"
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-orange-400 pl-4 my-3 italic text-gray-600 dark:text-gray-400">
      {children}
    </blockquote>
  ),
  code: ({ className, children }) => {
    const isInline = !className;
    if (isInline) {
      return (
        <code className="bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 px-1.5 py-0.5 rounded text-sm font-mono">
          {children}
        </code>
      );
    }
    return <code className={className}>{children}</code>;
  },
  pre: ({ children }) => (
    <pre className="bg-gray-800 dark:bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto my-3 text-sm">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-3">
      <table className="min-w-full border-collapse border border-gray-300 dark:border-gray-600">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-gray-100 dark:bg-gray-700">{children}</thead>
  ),
  th: ({ children }) => (
    <th className="border border-gray-300 dark:border-gray-600 px-3 py-2 text-left font-semibold">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-gray-300 dark:border-gray-600 px-3 py-2">
      {children}
    </td>
  ),
  hr: () => (
    <hr className="my-4 border-gray-300 dark:border-gray-600" />
  ),
  strong: ({ children }) => (
    <strong className="font-semibold">{children}</strong>
  ),
  em: ({ children }) => (
    <em className="italic">{children}</em>
  ),
};

const normalizeMarkdown = (content: string) => {
  const normalized = content
    .replace(/\r\n?/g, '\n')
    .trim();

  const replacements: Array<[RegExp, string]> = [
    [/(\*\*[^*\n]+?\*\*)\s*([*-]\s+|\d+\.\s+)/g, '$1\n$2'],
    [/([。！？!?:：])\s*([*-]\s+|\d+\.\s+)/g, '$1\n$2'],
    [/([^\n])(\#{1,}\s*)/g, '$1\n$2'],
    [/([^\n])((?:[*-]|\d+\.)\s+\*\*)/g, '$1\n$2'],
    [/(\*\*[^*]+\*\*)(?=\*\*)/g, '$1\n'],
  ];

  return replacements.reduce(
    (text, [pattern, replacement]) => text.replace(pattern, replacement),
    normalized
  );
};

export function MarkdownRenderer({ content, className = '' }: MarkdownRendererProps) {
  if (!content) return null;
  const normalized = normalizeMarkdown(content);

  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components}
      >
        {normalized}
      </ReactMarkdown>
    </div>
  );
}
