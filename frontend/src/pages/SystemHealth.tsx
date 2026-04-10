import { useEffect, useState } from 'react';
import { getSystemHealth, getOrchestratorStatus, type SystemHealth as HealthType, type OrchestratorStatus } from '../api';

export default function SystemHealth() {
  const [health, setHealth] = useState<HealthType | null>(null);
  const [status, setStatus] = useState<OrchestratorStatus | null>(null);

  const refresh = () => {
    getSystemHealth().then(setHealth).catch(() => {});
    getOrchestratorStatus().then(setStatus).catch(() => {});
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">System Health</h2>
        <button onClick={refresh}
          className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded text-sm text-gray-300 transition-colors">
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Ollama */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-3">Ollama</h3>
          <div className="flex items-center gap-2 mb-3">
            <div className={`w-2.5 h-2.5 rounded-full ${health?.ollama.status === 'online' ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-white font-medium">{health?.ollama.status || 'Unknown'}</span>
          </div>
          {health?.ollama.models && health.ollama.models.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-1">Available models:</p>
              <div className="space-y-1">
                {health.ollama.models.map((m) => (
                  <p key={m.name} className="text-xs text-gray-300 font-mono">{m.name}</p>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* CPU */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-3">CPU</h3>
          <p className="text-3xl font-semibold text-white">{health?.cpu_percent?.toFixed(0) || '—'}%</p>
          <div className="mt-2 w-full bg-gray-800 rounded-full h-2">
            <div className="bg-blue-500 h-2 rounded-full transition-all"
                 style={{ width: `${health?.cpu_percent || 0}%` }} />
          </div>
        </div>

        {/* Memory */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-3">Memory</h3>
          <p className="text-3xl font-semibold text-white">
            {health?.memory.used_gb || '—'}<span className="text-lg text-gray-500">/{health?.memory.total_gb || '—'} GB</span>
          </p>
          <div className="mt-2 w-full bg-gray-800 rounded-full h-2">
            <div className={`h-2 rounded-full transition-all ${
              (health?.memory.percent || 0) > 85 ? 'bg-red-500' : 'bg-green-500'
            }`}
                 style={{ width: `${health?.memory.percent || 0}%` }} />
          </div>
          <p className="text-xs text-gray-500 mt-1">{health?.memory.percent?.toFixed(0)}% used</p>
        </div>
      </div>

      {/* Orchestrator status */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
        <h3 className="text-sm font-medium text-gray-400 mb-3">Orchestrator</h3>
        <div className="grid grid-cols-4 gap-4 text-sm">
          <div>
            <p className="text-gray-500">Status</p>
            <p className="text-white font-medium">
              {status?.stopped ? 'Stopped' : status?.paused ? 'Paused' : status?.running ? 'Running' : 'Idle'}
            </p>
          </div>
          <div>
            <p className="text-gray-500">Current Step</p>
            <p className="text-white font-medium">{status?.current_step || 'None'}</p>
          </div>
          <div>
            <p className="text-gray-500">Current Cycle</p>
            <p className="text-white font-mono text-xs mt-0.5">{status?.current_cycle_id || 'None'}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
