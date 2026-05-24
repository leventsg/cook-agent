/**
 * Utility functions for date handling
 */

export type DateCategory = 'today' | 'yesterday' | 'lastWeek' | 'lastMonth' | 'older';

/**
 * Labels for date categories
 */
export const DATE_CATEGORY_LABELS: Record<DateCategory, string> = {
  today: 'Today',
  yesterday: 'Yesterday',
  lastWeek: 'Last 7 Days',
  lastMonth: 'Last 30 Days',
  older: 'Older',
};

/**
 * Categorize a date string into a relative time category
 */
export function getDateCategory(dateString: string): DateCategory {
  const date = new Date(dateString);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const lastWeekStart = new Date(today);
  lastWeekStart.setDate(lastWeekStart.getDate() - 7);
  const lastMonthStart = new Date(today);
  lastMonthStart.setDate(lastMonthStart.getDate() - 30);

  if (date >= today) return 'today';
  if (date >= yesterday) return 'yesterday';
  if (date >= lastWeekStart) return 'lastWeek';
  if (date >= lastMonthStart) return 'lastMonth';
  return 'older';
}

/**
 * Format a timestamp to a localized time string
 */
export function formatTime(date: Date, locale = 'zh-CN'): string {
  return date.toLocaleTimeString(locale, {
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Format a date to ISO string for API requests
 */
export function toISOString(date: Date): string {
  return date.toISOString();
}
