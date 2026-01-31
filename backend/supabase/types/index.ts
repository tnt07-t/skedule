// Database types for Skedule

export interface User {
  id: string;
  email: string;
  timezone: string;
  work_start_hour: number;
  work_end_hour: number;
  excluded_weekdays: number[];
  created_at: string;
  updated_at: string;
}

export interface CalendarToken {
  id: string;
  user_id: string;
  provider: 'google' | string;
  access_token: string;
  refresh_token_encrypted: string; // Never expose
  expires_at: string;
  scopes: string[];
  last_refreshed_at: string;
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: string;
  user_id: string;
  name: string;
  description?: string;
  difficulty: 1 | 2 | 3 | 4 | 5; // Mandatory
  focus_level: 1 | 2 | 3 | 4 | 5; // Mandatory
  time_preference?: 'morning' | 'afternoon' | 'evening' | 'flexible'; // Optional
  deadline: string; // Mandatory (ISO datetime)
  total_estimate_minutes?: number; // Set by LLM
  status: 'pending' | 'scheduled' | 'completed' | 'cancelled';
  created_at: string;
  updated_at: string;
}

export interface TaskSession {
  id: string;
  task_id: string;
  user_id: string;
  start_at: string;
  end_at: string;
  duration_minutes: number;
  calendar_event_id?: string; // Google Calendar event ID
  status: 'suggested' | 'scheduled' | 'completed' | 'cancelled';
  created_at: string;
  updated_at: string;
}

export interface Suggestion {
  id: string;
  task_id: string;
  user_id: string;
  llm_response_json: LLMResponse;
  total_estimated_minutes: number;
  confidence?: number; // 0.0 - 1.0
  chosen: boolean;
  created_at: string;
  updated_at: string;
}

export interface CalendarBusyBlock {
  id: string;
  user_id: string;
  start_at: string;
  end_at: string;
  event_title?: string;
  is_recurring: boolean;
  synced_at: string;
}

// LLM Response Schema
export interface LLMResponse {
  total_estimated_minutes: number;
  session_plan: SessionPlan[];
  alternative_options?: AlternativeOption[];
  reasoning?: string;
}

export interface SessionPlan {
  start: string; // ISO datetime
  end: string; // ISO datetime
  duration_minutes: number;
  reason?: string;
  confidence?: number;
}

export interface AlternativeOption {
  name: string;
  description: string;
  sessions: SessionPlan[];
  trade_off?: string;
}

// Request/Response Types
export interface CreateTaskRequest {
  name: string; // Mandatory
  difficulty: 1 | 2 | 3 | 4 | 5; // Mandatory
  focus_level: 1 | 2 | 3 | 4 | 5; // Mandatory
  deadline: string; // Mandatory (ISO datetime)
  description?: string; // Optional
  time_preference?: 'morning' | 'afternoon' | 'evening' | 'flexible'; // Optional
}

export interface ScheduleTaskRequest {
  task_id: string;
}

export interface ScheduleTaskResponse {
  suggestion_id: string;
  total_estimated_minutes: number;
  sessions: SessionPlan[];
  alternatives?: AlternativeOption[];
}

export interface AcceptScheduleRequest {
  suggestion_id: string;
}

export interface FreeBusyBlock {
  start_at: string;
  end_at: string;
  duration_minutes: number;
  weekday: string; // 'Monday', 'Tuesday', etc.
}
