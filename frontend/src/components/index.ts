// src/components/index.ts
/**
 * Components - Central export
 */

// Common components
export * from './common';

// Chat components
export * from './chat';

// Agent components
export * from './agent';

// Layout components
export * from './layout';

// Knowledge components
export { default as KnowledgePanel } from './KnowledgePanel';

// Legacy exports for backward compatibility
// These can be removed once all imports are updated
export { ChatInput } from './chat';
export { ChatWindow } from './chat';
export { MessageBubble } from './chat';
export { MarkdownRenderer } from './chat';
export { Sidebar } from './layout';

