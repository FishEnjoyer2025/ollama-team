import { useEffect, useState } from 'react';
import { getAgents, getAgent, type AgentInfo, type AgentDetail } from '../api';

export default function AgentProfiles() {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [selected, setSelected] = useState<AgentDetail | null>(null);

  useEffect(() => {
    getAgents().then((r) => setAgents(r.agents)).catch(() => {});
  }, []);

  const selectAgent = async (name: string) => {
    const detail = await getAgent(name);
    setSelected(detail);
  };

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-medium">Agent Profiles</h2>

      {/* Agent cards */}
      <div className="grid grid-cols-5 gap-3">
        {agents.map((agent) => {
          const successRate = agent.total_invocations > 0
            ? Math.round((agent.total_successes / agent.total_invocations) * 100)
            : 0;
          return (
            <button
              key={agent.name}
              onClick={() => selectAgent(agent.name)}
              className={`bg-gray-900 rounded-lg border p-4 text-left transition-colors hover:border-blue-500 ${
                selected?.name === agent.name ? 'border-blue-500' : 'border-gray-800'
              }`}
            >
              <h3 className="font-medium capitalize text-white">{agent.name}</h3>
              <div className="mt-2 space-y-1 text-xs text-gray-400">
                <p>Invocations: <span className="text-gray-200">{agent.total_invocations}</span></p>
                <p>Success rate: <span className={successRate >= 70 ? 'text-green-400' : successRate >= 40 ? 'text-yellow-400' : 'text-red-400'}>{successRate}%</span></p>
                <p>Avg time: <span className="text-gray-200">{agent.avg_duration_seconds.toFixed(1)}s</span></p>
              </div>
            </button>
          );
        })}
      </div>

      {/* Selected agent detail */}
      {selected && (
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-medium capitalize text-white">{selected.name}</h3>
            <button onClick={() => setSelected(null)} className="text-gray-500 hover:text-gray-300 text-sm">
              Close
            </button>
          </div>

          <div>
            <h4 className="text-xs text-gray-500 uppercase tracking-wider mb-2">Current System Prompt</h4>
            <pre className="bg-gray-950 rounded p-4 text-xs text-gray-300 overflow-x-auto max-h-96 overflow-y-auto whitespace-pre-wrap">
              {selected.prompt || 'No prompt file found'}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
