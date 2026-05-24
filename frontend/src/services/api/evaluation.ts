/**
 * API functions for RAG evaluation endpoints
 */

import { API_BASE } from '../../constants';
import { createAuthHeaders } from './client';
import type {
  EvaluationStatistics,
  TrendsResponse,
  AlertsResponse,
  EvaluationHealth,
  EvaluationDetail,
  ConversationEvaluationsResponse,
} from '../../types/evaluation';

/**
 * Get aggregated evaluation statistics
 */
export async function getEvaluationStatistics(
  token: string,
  startDate?: string,
  endDate?: string
): Promise<EvaluationStatistics> {
  const params = new URLSearchParams();
  if (startDate) params.append('start_date', startDate);
  if (endDate) params.append('end_date', endDate);

  const queryString = params.toString();
  const url = `${API_BASE}/evaluation/statistics${queryString ? `?${queryString}` : ''}`;

  const response = await fetch(url, {
    headers: createAuthHeaders(token),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch evaluation statistics: ${response.status}`);
  }

  return response.json();
}

/**
 * Get evaluation trends over time
 */
export async function getEvaluationTrends(
  token: string,
  days: number = 7,
  granularity: 'day' | 'hour' = 'day'
): Promise<TrendsResponse> {
  const params = new URLSearchParams({
    days: days.toString(),
    granularity,
  });

  const response = await fetch(`${API_BASE}/evaluation/trends?${params}`, {
    headers: createAuthHeaders(token),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch evaluation trends: ${response.status}`);
  }

  return response.json();
}

/**
 * Get quality alerts (evaluations below thresholds)
 */
export async function getEvaluationAlerts(
  token: string,
  limit: number = 50
): Promise<AlertsResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
  });

  const response = await fetch(`${API_BASE}/evaluation/alerts?${params}`, {
    headers: createAuthHeaders(token),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch evaluation alerts: ${response.status}`);
  }

  return response.json();
}

/**
 * Get evaluation system health status
 */
export async function getEvaluationHealth(token: string): Promise<EvaluationHealth> {
  const response = await fetch(`${API_BASE}/evaluation/health`, {
    headers: createAuthHeaders(token),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch evaluation health: ${response.status}`);
  }

  return response.json();
}

/**
 * Get a single evaluation by ID
 */
export async function getEvaluationById(
  token: string,
  evaluationId: string
): Promise<EvaluationDetail> {
  const response = await fetch(`${API_BASE}/evaluation/${evaluationId}`, {
    headers: createAuthHeaders(token),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch evaluation: ${response.status}`);
  }

  return response.json();
}

/**
 * Get all evaluations for a conversation
 */
export async function getConversationEvaluations(
  token: string,
  conversationId: string,
  limit: number = 100
): Promise<ConversationEvaluationsResponse> {
  const params = new URLSearchParams({
    limit: limit.toString(),
  });

  const response = await fetch(
    `${API_BASE}/evaluation/conversation/${conversationId}?${params}`,
    {
      headers: createAuthHeaders(token),
    }
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch conversation evaluations: ${response.status}`);
  }

  return response.json();
}
