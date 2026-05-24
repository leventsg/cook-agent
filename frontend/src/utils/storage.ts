/**
 * Utility functions for local storage
 */

import { STORAGE_KEYS } from '../constants';

/**
 * Get an item from localStorage with error handling
 */
export function getStorageItem<T>(key: string): T | null {
  try {
    const item = localStorage.getItem(key);
    return item ? JSON.parse(item) : null;
  } catch {
    return null;
  }
}

/**
 * Set an item in localStorage with error handling
 */
export function setStorageItem<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.warn(`Failed to save to localStorage: ${key}`, error);
  }
}

/**
 * Remove an item from localStorage
 */
export function removeStorageItem(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch (error) {
    console.warn(`Failed to remove from localStorage: ${key}`, error);
  }
}

/**
 * Get a string item from localStorage (no JSON parsing)
 */
export function getStorageString(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

/**
 * Set a string item in localStorage (no JSON stringifying)
 */
export function setStorageString(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch (error) {
    console.warn(`Failed to save to localStorage: ${key}`, error);
  }
}

// Theme-specific helpers
export function getStoredTheme(): 'light' | 'dark' | null {
  const theme = getStorageString(STORAGE_KEYS.THEME);
  return theme === 'light' || theme === 'dark' ? theme : null;
}

export function setStoredTheme(theme: 'light' | 'dark'): void {
  setStorageString(STORAGE_KEYS.THEME, theme);
}

// Auth-specific helpers
export function getStoredToken(): string | null {
  return getStorageString(STORAGE_KEYS.TOKEN);
}

export function setStoredToken(token: string): void {
  setStorageString(STORAGE_KEYS.TOKEN, token);
}

export function removeStoredToken(): void {
  removeStorageItem(STORAGE_KEYS.TOKEN);
}

export function getStoredUsername(): string | null {
  return getStorageString(STORAGE_KEYS.USERNAME);
}

export function setStoredUsername(username: string): void {
  setStorageString(STORAGE_KEYS.USERNAME, username);
}

export function removeStoredUsername(): void {
  removeStorageItem(STORAGE_KEYS.USERNAME);
}
