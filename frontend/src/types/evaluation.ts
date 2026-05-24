/**
 * Types for RAG Evaluation data
 */

// Metric statistics with mean/min/max values
export interface MetricStats {
  mean: number | null;
  min?: number | null;
  max?: number | null;
}

// Aggregated evaluation statistics
export interface EvaluationStatistics {
  total_evaluations: number;
  pending_count: number;
  failed_count: number;
  period: {
    start: string | null;
    end: string | null;
  };
  metrics: {
    faithfulness: MetricStats;
    answer_relevancy: MetricStats;
  };
  avg_evaluation_duration_ms: number | null;
}

// Single trend data point
export interface TrendDataPoint {
  period: string;
  count: number;
  metrics: {
    faithfulness: number | null;
    answer_relevancy: number | null;
  };
}

// Trends response from API
export interface TrendsResponse {
  period_days: number;
  granularity: string;
  data_points: number;
  trends: TrendDataPoint[];
}

// Single evaluation alert
export interface EvaluationAlert {
  id: string;
  message_id: string;
  conversation_id: string;
  user_id: string | null;
  query: string;
  rewritten_query: string | null;
  context: string;
  response: string;
  faithfulness: number | null;
  answer_relevancy: number | null;
  evaluation_status: string;
  error_message: string | null;
  evaluation_duration_ms: number | null;
  created_at: string;
  evaluated_at: string | null;
  violated_thresholds: string[];
}

// Alerts response from API
export interface AlertsResponse {
  thresholds: Record<string, number>;
  count: number;
  alerts: EvaluationAlert[];
}

// Health check response
export interface EvaluationHealth {
  enabled: boolean;
  async_mode: boolean;
  sample_rate: number;
  configured_metrics: string[];
  timeout_seconds: number;
  alert_thresholds: Record<string, number>;
}

// Single evaluation detail
export interface EvaluationDetail {
  id: string;
  message_id: string;
  conversation_id: string;
  user_id: string | null;
  query: string;
  rewritten_query: string | null;
  context: string;
  response: string;
  faithfulness: number | null;
  answer_relevancy: number | null;
  evaluation_status: string;
  error_message: string | null;
  evaluation_duration_ms: number | null;
  created_at: string;
  evaluated_at: string | null;
}

// Conversation evaluations response
export interface ConversationEvaluationsResponse {
  conversation_id: string;
  count: number;
  evaluations: EvaluationDetail[];
}
