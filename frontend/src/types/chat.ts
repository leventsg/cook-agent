/**
 * Chat-related type definitions
 */

import type { ImageData } from './api';

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  timestamp: Date;
  sources?: Source[];
  intent?: IntentInfo | string;
  isStreaming?: boolean;
  thinking?: string[];
  // Timing information for response tracking
  thinkingStartTime?: number; // Unix timestamp in ms when thinking started
  thinkingEndTime?: number;   // Unix timestamp in ms when thinking ended
  answerStartTime?: number;   // Unix timestamp in ms when answer generation started
  answerEndTime?: number;     // Unix timestamp in ms when answer generation ended
  // Image attachments (base64 encoded)
  images?: string[];
  // Vision analysis result
  vision?: VisionInfo;
  
  // Agent specific fields
  agent_session_id?: string;
  trace?: any[]; // Agent execution trace
}

/**
 * Unified source structure for both RAG and Web search results.
 * 
 * @property type - "rag" for knowledge base, "web" for web search
 * @property info - Display text describing the source
 * @property url - Optional URL (primarily for web sources, clickable link)
 */
export interface Source {
  type: 'rag' | 'web' | string;
  info: string;
  url?: string;
}

export interface IntentInfo {
  need_rag: boolean;
  intent: string;
  reason: string;
}

/**
 * Vision analysis result from image processing.
 */
export interface VisionInfo {
  is_food_related: boolean;
  intent: string;
  description: string;
  extracted_info?: {
    dish_name?: string;
    ingredients?: string[];
    cooking_stage?: string;
    other?: string;
  };
  direct_response?: string;
  confidence: number;
}

export interface ConversationSummary {
  id: string;
  title?: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string | null;
}


export interface Conversation {
  id: string;
  messages: Message[];
  createdAt: Date;
}

export interface AgentChatRequest {
  message: string;
  images?: ImageData[];  // Images for multimodal understanding
  session_id?: string;
  agent_name?: string;
  stream?: boolean;
  selected_tools?: string[];  // User-selected tools
}

export interface ToolSchema {
  name: string;
  description: string;
}

export interface ServerInfo {
  name: string;
  type: 'local' | 'mcp';
  tools: ToolSchema[];
}

export interface ToolsListResponse {
  servers: ServerInfo[];
}

export interface MCPServer {
  id: string;
  name: string;
  endpoint: string;
  auth_header_name?: string | null;
  auth_token?: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface MCPServerListResponse {
  servers: MCPServer[];
}

export interface MCPServerUpdateRequest {
  endpoint?: string;
  auth_header_name?: string | null;
  auth_token?: string | null;
  enabled?: boolean;
}

export interface AgentSessionResponse {
  id: string;
  user_id: string;
  title?: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string | null;
}

export interface AgentMessageResponse {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  created_at: string;
  trace?: any[];
  tool_calls?: any[];
  tool_call_id?: string;
  tool_name?: string;
  thinking_duration_ms?: number;
  answer_duration_ms?: number;
}

export interface AgentSessionListResponse {
  sessions: AgentSessionResponse[];
  total_count: number;
  limit: number;
  offset: number;
}

export interface AgentHistoryResponse {
  session_id: string;
  messages: AgentMessageResponse[];
}

// Streaming state for conversation caching
export interface StreamingState {
  conversationId: string;
  messages: Message[];
  isStreaming: boolean;
  tempId?: string;
}

// ==================== Subagent Types ====================

/**
 * Subagent configuration schema from API.
 */
export interface SubagentSchema {
  name: string;
  display_name: string;
  description: string;
  system_prompt?: string;
  tools: string[];
  max_iterations: number;
  enabled: boolean;
  builtin: boolean;
  category: string;
}

/**
 * Response from list subagents API.
 */
export interface SubagentListResponse {
  subagents: SubagentSchema[];
}

/**
 * Request to toggle a subagent's enabled status.
 */
export interface SubagentToggleRequest {
  enabled: boolean;
}

/**
 * Request to create a custom subagent.
 */
export interface CreateSubagentRequest {
  name: string;
  display_name: string;
  description: string;
  system_prompt: string;
  tools?: string[];
  max_iterations?: number;
  category?: string;
}

/**
 * Request to update a custom subagent.
 */
export interface UpdateSubagentRequest {
  display_name?: string;
  description?: string;
  system_prompt?: string;
  tools?: string[];
  max_iterations?: number;
  category?: string;
}
