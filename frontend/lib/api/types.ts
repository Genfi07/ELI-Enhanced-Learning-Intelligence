export type UserRole = "USER" | "MODERATOR" | "ADMIN" | "SUPER_ADMIN";
export type UserStatus = "ACTIVE" | "BLOCKED" | "DELETED";

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  profile_image_url?: string | null;
  last_login_at?: string | null;
  preferences?: Record<string, unknown>;
}

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface Conversation {
  id: string;
  title: string;
  model: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export type MessageRole = "user" | "assistant" | "system" | "tool";

export interface Message {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  tokens_in: number;
  tokens_out: number;
  model: string | null;
  created_at: string;
}

// --------------------------------------------------------------------------- //
// Memory
// --------------------------------------------------------------------------- //
export type MemoryType =
  | "FACT"
  | "PREFERENCE"
  | "GOAL"
  | "INSTRUCTION"
  | "EPISODE";

export type MemoryStatus = "ACTIVE" | "SUPERSEDED" | "DELETED";

export interface Memory {
  id: string;
  type: MemoryType;
  content: string;
  importance: number;
  confidence: number;
  source?: string | null;
  status: MemoryStatus;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
  usage_count: number;
}

// --------------------------------------------------------------------------- //
// Documents
// --------------------------------------------------------------------------- //
export type DocumentStatus =
  | "PENDING"
  | "PROCESSING"
  | "READY"
  | "FAILED";

export interface Document {
  id: string;
  title: string;
  mime_type: string;
  size_bytes: number;
  status: DocumentStatus;
  error?: string | null;
  chunk_count: number;
  summary: string | null;
  topics: string[];
  created_at: string;
  deleted_at: string | null;
  hidden_at: string | null;
}

// --------------------------------------------------------------------------- //
// Goals
// --------------------------------------------------------------------------- //
export type GoalKind =
  | "LEARN"
  | "EXPLORE"
  | "IMPROVE"
  | "CONNECT"
  | "PROPOSE";

export type GoalStatus =
  | "ACTIVE"
  | "ACHIEVED"
  | "ABANDONED"
  | "PAUSED";

export interface Goal {
  id: string;
  kind: GoalKind;
  content: string;
  status: GoalStatus;
  progress: number;
  origin?: string | null;
  priority?: number | null;
  related_topics?: string[];
  progress_notes?: string | null;
  achieved_at?: string | null;
  abandoned_at?: string | null;
  created_at: string;
  updated_at?: string;
}

// --------------------------------------------------------------------------- //
// Tools
// --------------------------------------------------------------------------- //
export interface Tool {
  name: string;
  description: string;
  min_autonomy_level: number;
  requires_confirmation: boolean;
  timeout_ms: number;
  enabled: boolean;
  scope: string;
}

export interface ToolInvokeResult {
  tool_name: string;
  status: string;
  result: unknown;
  error: string | null;
  latency_ms: number;
  pending_action_id: string | null;
}

// --------------------------------------------------------------------------- //
// Admin
// --------------------------------------------------------------------------- //
export interface AdminUser {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  created_at: string;
  last_login_at: string | null;
}

export interface AnalyticsOverview {
  users_total: number;
  users_active: number;
  users_blocked: number;
  conversations_total: number;
  messages_total: number;
  memories_total: number;
  documents_total: number;
  tool_calls_total: number;
  tokens_total: number;
  cost_estimate_usd: number;
  errors_total: number;
}

export interface TimeseriesPoint {
  date: string;
  messages: number;
  tokens: number;
  errors: number;
}

export interface Timeseries {
  days: number;
  points: TimeseriesPoint[];
}

export interface SystemHealth {
  status: string;
  database: string;
  llm_provider: string;
  embeddings_provider: string;
  tools_count: number;
  env: string;
  version: string;
}

export interface AuditLogEntry {
  id: string;
  actor_user_id: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  before: unknown;
  after: unknown;
  meta: Record<string, unknown>;
  created_at: string;
}

export interface SettingItem {
  key: string;
  value: unknown;
  default: unknown;
  is_override: boolean;
  is_secret?: boolean;
  category: string;
  description: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

// --------------------------------------------------------------------------- //
// Admin A2 — Conversaciones globales / detalle de usuario
// --------------------------------------------------------------------------- //
export interface AdminConversation {
  id: string;
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  title: string;
  model: string | null;
  status: string;
  messages_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminMessage {
  id: string;
  role: string;
  content: string;
  tokens_in: number;
  tokens_out: number;
  model: string | null;
  created_at: string;
}

export interface AdminUserStats {
  conversations_total: number;
  messages_total: number;
  tokens_in_total: number;
  tokens_out_total: number;
  cost_estimate_usd: number;
  memories_active: number;
  documents_active: number;
  last_activity_at: string | null;
}

export interface AdminMemory {
  id: string;
  type: string;
  content: string;
  importance: number;
  confidence: number;
  status: string;
  created_at: string;
  last_used_at: string | null;
}

export interface AdminDocument {
  id: string;
  title: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  chunk_count: number;
  created_at: string;
  deleted_at: string | null;
  hidden_at: string | null;
}

export interface AdminUserDetail {
  user: AdminUser;
  stats: AdminUserStats;
  recent_conversations: AdminConversation[];
  recent_memories: AdminMemory[];
  recent_documents: AdminDocument[];
}

export interface GuideEntry {
  key: string;
  category: string;
  short: string;
  description: string;
  values?: string | null;
  impact?: string | null;
  example?: string | null;
}