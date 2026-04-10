const BASE = 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// Cycles
export const getCycles = (params?: { status?: string; limit?: number; offset?: number }) => {
  const q = new URLSearchParams();
  if (params?.status) q.set('status', params.status);
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));
  return request<{ cycles: Cycle[]; limit: number; offset: number }>(`/api/cycles?${q}`);
};

export const getCycle = (id: string) =>
  request<{ cycle: Cycle; feedback: Feedback[] }>(`/api/cycles/${id}`);

export const submitFeedback = (cycleId: string, rating: 'up' | 'down', note?: string) =>
  request<Feedback>(`/api/cycles/${cycleId}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ rating, note }),
  });

// Agents
export const getAgents = () => request<{ agents: AgentInfo[] }>('/api/agents');
export const getAgent = (name: string) => request<AgentDetail>(`/api/agents/${name}`);

// System
export const getSystemHealth = () => request<SystemHealth>('/api/system/health');
export const getOrchestratorStatus = () => request<OrchestratorStatus>('/api/system/status');
export const pauseLoop = () => request<{ status: string }>('/api/system/pause', { method: 'POST' });
export const resumeLoop = () => request<{ status: string }>('/api/system/resume', { method: 'POST' });
export const stopLoop = () => request<{ status: string }>('/api/system/stop', { method: 'POST' });
export const triggerCycle = () => request<{ cycle_id: string }>('/api/system/trigger', { method: 'POST' });

// Guidance
export const getGuidance = () => request<{ message: string }>('/api/system/guidance');
export const setGuidance = (message: string) =>
  request<{ status: string }>('/api/system/guidance', {
    method: 'POST',
    body: JSON.stringify({ message }),
  });

// Settings
export const getSettings = () => request<Record<string, string>>('/api/settings');
export const updateSettings = (updates: Record<string, string | number | boolean>) =>
  request<Record<string, string>>('/api/settings', {
    method: 'PUT',
    body: JSON.stringify(updates),
  });

// Types
export interface Cycle {
  id: string;
  started_at: string;
  completed_at: string | null;
  status: 'running' | 'success' | 'failed' | 'rolled_back' | 'abandoned';
  proposal: { description: string; files: string[]; expected_outcome: string; risk: string } | null;
  branch_name: string | null;
  diff: string | null;
  test_output: string | null;
  deploy_log: string | null;
  rollback_reason: string | null;
}

export interface Feedback {
  id: number;
  cycle_id: string;
  timestamp: string;
  rating: 'up' | 'down';
  change_summary: string | null;
  note: string | null;
}

export interface AgentInfo {
  name: string;
  total_invocations: number;
  total_successes: number;
  total_failures: number;
  avg_duration_seconds: number;
  last_invoked_at: string | null;
}

export interface AgentDetail extends AgentInfo {
  prompt: string;
  stats: Record<string, unknown>;
}

export interface SystemHealth {
  ollama: { status: string; models: { name: string }[] };
  cpu_percent: number;
  memory: { total_gb: number; used_gb: number; percent: number };
}

export interface OrchestratorStatus {
  running: boolean;
  paused: boolean;
  stopped: boolean;
  current_step: string | null;
  current_cycle_id: string | null;
}
