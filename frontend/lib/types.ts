export interface Session {
  id: string;
  name: string;
  repo_path: string;
  repo_url?: string | null;
  branch?: string | null;
  status: "running" | "passed" | "failed" | "stopped";
  created_at: string;
  completed_at: string | null;
  total_iterations: number;
  total_tokens: number;
  total_cost_usd: number;
  max_iterations: number;
  model: string;
  verify_command: string;
}

export interface Task {
  id: string;
  session_id: string;
  title: string;
  spec: string;
  files_context: string; // JSON
  created_at: string;
}

export interface Iteration {
  id: string;
  session_id: string;
  iteration_number: number;
  status: "running" | "passed" | "failed";
  agent_output: string;
  files_changed: string; // JSON
  verify_output: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  duration_seconds: number;
  git_commit_hash: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface SessionDetail extends Session {
  task: Task | null;
  iterations: Iteration[];
}

export interface AnalyticsSummary {
  total_sessions: number;
  total_passed: number;
  success_rate: number;
  avg_iterations_to_pass: number;
  total_cost_usd: number;
  total_tokens: number;
  avg_cost_per_session: number;
  correction_tax_avg_iterations: number;
}

export interface RepoNode {
  path: string;
  group: string;
  is_test: boolean;
  size: number;
  symbols: { name: string; line: number }[];
}

export interface RepoMap {
  nodes: RepoNode[];
  edges: { from: string; to: string }[];
  layers: Record<string, number>;
  truncated: boolean;
}

export type AgentEventKind = "focus" | "tool" | "file_changed";

export interface AgentEvent {
  id: number;
  kind: AgentEventKind;
  iteration?: number;
  // focus
  files?: { path: string; reason: string }[];
  tests_passing?: boolean;
  // tool
  tool?: string;
  target?: string;
  error?: string | null;
  passed?: boolean | null;
  // file_changed
  path?: string;
  is_new?: boolean;
  added?: number;
  removed?: number;
  diff?: string;
  diff_cut_off?: boolean;
}

export interface WsMessage {
  event: "iteration_start" | "iteration_complete" | "verify_output" | "session_complete" | "agent_token" | "cancelled" | "cascade" | "setup" | AgentEventKind;
  data: Record<string, unknown>;
  message_id?: string;
}

// A step of a cascade session (backend core/cascade.py), saved as an event of kind "cascade"
export interface CascadeStep {
  id: number;
  kind: "cascade";
  step: "scout" | "cheap" | "review" | "reviewed" | "escalated";
  model: string;
  notes?: string;
  accept?: boolean;
  why?: string;
  edited_tests?: string[];
  reason?: string;
  cheap_iterations?: number;
  cost_usd?: number;
}

export interface ChatSession {
  id: string;
  name: string;
  repo_path: string;
  verify_command: string;
  model: string;
  max_iterations: number;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  chat_session_id: string;
  prompt: string;
  status: "running" | "passed" | "failed";
  loop_session_id: string | null;
  total_iterations: number;
  total_cost_usd: number;
  git_commit_hash: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[];
}
