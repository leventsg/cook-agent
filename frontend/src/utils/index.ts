/**
 * Utility functions
 */

export * from './date';
export * from './storage';

/**
 * Generate a unique ID for messages
 */
export function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substr(2);
}

/**
 * Wait for the next tick (useful for async operations)
 */
export const waitForNextTick = (): Promise<void> =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, 0);
  });

/**
 * Capitalize the first letter of a string
 */
export function capitalize(str: string): string {
  if (!str) return str;
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Truncate a string to a maximum length
 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength) + '...';
}

/**
 * Check if a conversation ID is temporary (not yet saved to server)
 */
export function isTempConversationId(id: string): boolean {
  return id.startsWith('temp-');
}
