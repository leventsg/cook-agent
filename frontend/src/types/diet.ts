/**
 * Diet types for frontend
 */

import type { ImageData } from './api';

export interface Dish {
  name: string;
  weight_g?: number;
  unit?: string;
  calories?: number;
  protein?: number;
  fat?: number;
  carbs?: number;
}

export interface DietPlanMeal {
  id: string;
  plan_date: string;
  meal_type: string;
  dishes?: Dish[];
  total_calories?: number;
  total_protein?: number;
  total_fat?: number;
  total_carbs?: number;
  notes?: string;
}

export interface DietPlan {
  user_id: string;
  week_start_date: string;
  meals?: DietPlanMeal[];
}

export interface FoodItem {
  id: string;
  log_id: string;
  food_name: string;
  weight_g?: number;
  unit?: string;
  calories?: number;
  protein?: number;
  fat?: number;
  carbs?: number;
  source: string;
  confidence_score?: number;
  created_at: string;
}

export interface DietLog {
  id: string;
  user_id: string;
  log_date: string;
  meal_type: string;
  plan_meal_id?: string;
  total_calories?: number;
  total_protein?: number;
  total_fat?: number;
  total_carbs?: number;
  notes?: string;
  items?: FoodItem[];
  created_at: string;
  updated_at: string;
}

export interface DailySummary {
  date: string;
  total_calories: number;
  total_protein: number;
  total_fat: number;
  total_carbs: number;
  meals_logged: string[];
  log_count: number;
}

export interface WeeklySummary {
  week_start_date: string;
  week_end_date: string;
  daily_data: Record<string, {
    calories: number;
    protein: number;
    fat: number;
    carbs: number;
    meals: string[];
  }>;
  total_calories: number;
  total_protein: number;
  total_fat: number;
  total_carbs: number;
  avg_daily_calories: number;
}

export interface DeviationAnalysis {
  has_plan: boolean;
  message?: string;
  week_start_date?: string;
  total_plan_calories?: number;
  total_actual_calories?: number;
  total_deviation?: number;
  total_deviation_pct?: number;
  meal_deviations?: Array<{
    meal_key: string;
    plan_calories: number;
    actual_calories: number;
    calories_deviation: number;
    calories_deviation_pct: number;
  }>;
  execution_rate?: number;
}

export interface UserFoodPreference {
  id: string;
  user_id: string;
  common_foods?: Array<{ name: string; frequency?: number; avg_weight?: number }>;
  avoided_foods?: string[];
  diet_tags?: string[];
  avg_daily_calories_min?: number;
  avg_daily_calories_max?: number;
  deviation_patterns?: Array<{ meal_type: string; deviation_rate?: number }>;
  stats?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AddMealRequest {
  plan_date: string;
  meal_type: string;
  dishes?: Dish[];
  notes?: string;
}

export interface UpdateMealRequest {
  dishes?: Dish[];
  notes?: string;
}

export interface CreateLogRequest {
  log_date: string;
  meal_type: string;
  items?: Array<{
    food_name: string;
    weight_g?: number;
    unit?: string;
    calories?: number;
    protein?: number;
    fat?: number;
    carbs?: number;
  }>;
  plan_meal_id?: string;
  notes?: string;
}

export interface UpdateLogRequest {
  log_date?: string;
  meal_type?: string;
  items?: Array<{
    food_name: string;
    weight_g?: number;
    unit?: string;
    calories?: number;
    protein?: number;
    fat?: number;
    carbs?: number;
  }>;
  notes?: string;
}

export interface LogFromTextRequest {
  text: string;
  images?: ImageData[];
  log_date?: string;
  meal_type?: string;
}

export interface MarkMealEatenRequest {
  log_date?: string;
}

export interface UpdatePreferenceRequest {
  dietary_restrictions?: string[];
  allergies?: string[];
  favorite_cuisines?: string[];
  avoided_foods?: string[];
  disliked_foods?: string[];
  preferred_foods?: string[];
  calorie_goal?: number;
  protein_goal?: number;
  fat_goal?: number;
  carbs_goal?: number;
}
