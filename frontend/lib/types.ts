export interface Session {
  id: string;
  name: string;
  repo_path: string;
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

export interface WsMessage {
  event: "iteration_start" | "iteration_complete" | "verify_output" | "session_complete" | "agent_token" | "cancelled";
  data: Record<string, unknown>;
  message_id?: string;
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
