/**
 * Application constants
 */

// API Configuration
export const API_BASE = '/api/v1';

// Pagination
export const CONVERSATIONS_PAGE_SIZE = 30;

// Storage Keys
export const STORAGE_KEYS = {
  TOKEN: 'cookhero_token',
  USERNAME: 'cookhero_username',
  THEME: 'theme',
  STREAMING_CACHE: 'cookhero_streaming_cache',
} as const;

// Intent Labels
export const INTENT_LABELS: Record<string, string> = {
  recipe_search: '菜谱搜索',
  cooking_tips: '烹饪技巧',
  ingredient_info: '食材信息',
  recommendation: '菜品推荐',
  general_chat: '闲聊',
};

// Date Category Labels
export const DATE_CATEGORY_LABELS = {
  today: 'Today',
  yesterday: 'Yesterday',
  lastWeek: 'Last 7 Days',
  lastMonth: 'Last 30 Days',
  older: 'Older',
} as const;

// App Info
export const APP_NAME = 'CookHero';
export const APP_EMOJI = '🍳';
