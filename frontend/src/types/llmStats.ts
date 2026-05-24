/**
 * TypeScript types for LLM usage statistics
 */

/**
 * Summary statistics for LLM usage
 */
export interface LLMStatsSummary {
  total_calls: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  avg_tokens_per_call: number;
  avg_duration_ms: number;
  period: {
    start: string | null;
    end: string | null;
  };
}

/**
 * Time series data point for LLM usage
 */
export interface TimeSeriesDataPoint {
  period: string;
  call_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  avg_duration_ms: number;
}

/**
 * Response from time series endpoint
 */
export interface TimeSeriesResponse {
  period_days: number;
  granularity: 'day' | 'hour';
  data_points: number;
  time_series: TimeSeriesDataPoint[];
}

/**
 * Module distribution data
 */
export interface ModuleDistribution {
  module_name: string;
  call_count: number;
  total_tokens: number;
  avg_tokens: number;
  avg_duration_ms: number;
}

/**
 * Response from module distribution endpoint
 */
export interface ModuleDistributionResponse {
  distribution: ModuleDistribution[];
  count: number;
}

/**
 * Model distribution data
 */
export interface ModelDistribution {
  model_name: string;
  call_count: number;
  total_tokens: number;
  avg_tokens: number;
  avg_duration_ms: number;
}

/**
 * Response from model distribution endpoint
 */
export interface ModelDistributionResponse {
  distribution: ModelDistribution[];
  count: number;
}

/**
 * Single LLM usage log entry
 */
export interface LLMUsageLog {
  id: string;
  request_id: string;
  module_name: string;
  user_id: string | null;
  conversation_id: string | null;
  model_name: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  duration_ms: number | null;
  created_at: string;
}

/**
 * Response from conversation LLM stats endpoint
 */
export interface ConversationLLMStatsResponse {
  conversation_id: string;
  count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  logs: LLMUsageLog[];
}

/**
 * Response from modules list endpoint
 */
export interface ModulesListResponse {
  modules: string[];
  count: number;
}

/**
 * Response from models list endpoint
 */
export interface ModelsListResponse {
  models: string[];
  count: number;
}

/**
 * Tool distribution data
 */
export interface ToolDistribution {
  tool_name: string;
  call_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  avg_tokens: number;
  avg_duration_ms: number;
}

/**
 * Response from tool distribution endpoint
 */
export interface ToolDistributionResponse {
  distribution: ToolDistribution[];
  count: number;
}

/**
 * Response from tools list endpoint
 */
export interface ToolsListResponse {
  tools: string[];
  count: number;
}

/**
 * Time series data point for tool usage
 */
export interface ToolTimeSeriesDataPoint extends TimeSeriesDataPoint {
  tool_name: string;
}
