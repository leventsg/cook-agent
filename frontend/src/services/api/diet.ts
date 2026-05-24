/**
 * Diet API service
 */

import { apiGet, apiPost, apiDelete } from './client';
import { API_BASE } from '../../constants';
import type {
  DietPlan,
  DietLog,
  DailySummary,
  WeeklySummary,
  DeviationAnalysis,
  UserFoodPreference,
  AddMealRequest,
  UpdateMealRequest,
  CreateLogRequest,
  LogFromTextRequest,
  MarkMealEatenRequest,
  UpdateLogRequest,
  UpdatePreferenceRequest,
} from '../../types/diet';

const DIET_BASE = '/diet';

// ==================== Plan APIs ====================

/**
 * Get plan meals by week start date
 */
export async function getPlanByWeek(
  token: string,
  weekStartDate: string
): Promise<{ plan: DietPlan | null }> {
  const query = new URLSearchParams({ week_start_date: weekStartDate });
  return apiGet(`${DIET_BASE}/plans/by-week?${query.toString()}`, token);
}

// ==================== Meal APIs ====================

/**
 * Add meal to plan
 */
export async function addMealToPlan(
  token: string,
  data: AddMealRequest
): Promise<void> {
  await apiPost(`${DIET_BASE}/plans/meals`, data, token);
}

/**
 * Update meal
 */
export async function updateMeal(
  token: string,
  mealId: string,
  data: UpdateMealRequest
): Promise<void> {
  const response = await fetch(`${API_BASE}${DIET_BASE}/meals/${mealId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error('Failed to update meal');
  }
}

/**
 * Delete meal
 */
export async function deleteMeal(token: string, mealId: string): Promise<void> {
  await apiDelete(`${DIET_BASE}/meals/${mealId}`, token);
}

/**
 * Copy meal
 */
export async function copyMeal(
  token: string,
  mealId: string,
  targetDate: string,
  targetMealType?: string
): Promise<void> {
  await apiPost(`${DIET_BASE}/meals/${mealId}/copy`, {
    target_date: targetDate,
    target_meal_type: targetMealType,
  }, token);
}

/**
 * Mark meal as eaten
 */
export async function markMealEaten(
  token: string,
  mealId: string,
  data: MarkMealEatenRequest
): Promise<DietLog> {
  return apiPost<DietLog>(`${DIET_BASE}/meals/${mealId}/mark-eaten`, data, token);
}

// ==================== Log APIs ====================

/**
 * Get logs by date
 */
export async function getLogsByDate(
  token: string,
  logDate: string
): Promise<{ logs: DietLog[]; date: string }> {
  return apiGet(`${DIET_BASE}/logs?log_date=${logDate}`, token);
}

/**
 * Create log
 */
export async function createLog(token: string, data: CreateLogRequest): Promise<DietLog> {
  return apiPost<DietLog>(`${DIET_BASE}/logs`, data, token);
}

/**
 * Create log from text (AI parsing)
 */
export async function createLogFromText(
  token: string,
  data: LogFromTextRequest
): Promise<DietLog> {
  return apiPost<DietLog>(`${DIET_BASE}/logs/from-text`, data, token);
}

/**
 * Get log by ID
 */
export async function getLog(token: string, logId: string): Promise<DietLog> {
  return apiGet<DietLog>(`${DIET_BASE}/logs/${logId}`, token);
}

/**
 * Delete log
 */
export async function deleteLog(token: string, logId: string): Promise<void> {
  await apiDelete(`${DIET_BASE}/logs/${logId}`, token);
}

/**
 * Update log
 */
export async function updateLog(
  token: string,
  logId: string,
  data: UpdateLogRequest
): Promise<DietLog> {
  const response = await fetch(`${API_BASE}${DIET_BASE}/logs/${logId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error('Failed to update log');
  }

  return response.json();
}

// ==================== Analysis APIs ====================

/**
 * Get daily summary
 */
export async function getDailySummary(
  token: string,
  targetDate: string
): Promise<DailySummary> {
  return apiGet(`${DIET_BASE}/analysis/daily?target_date=${targetDate}`, token);
}

/**
 * Get weekly summary
 */
export async function getWeeklySummary(
  token: string,
  weekStartDate?: string
): Promise<WeeklySummary> {
  const query = weekStartDate ? `?week_start_date=${weekStartDate}` : '';
  return apiGet(`${DIET_BASE}/analysis/weekly${query}`, token);
}

/**
 * Get deviation analysis
 */
export async function getDeviationAnalysis(
  token: string,
  weekStartDate?: string
): Promise<DeviationAnalysis> {
  const query = weekStartDate ? `?week_start_date=${weekStartDate}` : '';
  return apiGet(`${DIET_BASE}/analysis/deviation${query}`, token);
}

// ==================== Preference APIs ====================

/**
 * Get user preferences
 */
export async function getPreferences(
  token: string
): Promise<{ preference: UserFoodPreference | null }> {
  return apiGet(`${DIET_BASE}/preferences`, token);
}

/**
 * Update user preferences
 */
export async function updatePreferences(
  token: string,
  data: UpdatePreferenceRequest
): Promise<{ preference: UserFoodPreference }> {
  const response = await fetch(`${API_BASE}${DIET_BASE}/preferences`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error('Failed to update preferences');
  }

  return response.json();
}

// ==================== Enums API ====================

/**
 * Get enum values
 */
export async function getEnums(): Promise<{
  meal_types: Array<{ value: string; label: string }>;
  days_of_week: Array<{ value: number; label: string }>;
  plan_statuses: Array<{ value: string; label: string }>;
  data_sources: Array<{ value: string; label: string }>;
}> {
  return apiGet(`${DIET_BASE}/enums`);
}
