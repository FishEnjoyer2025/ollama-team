import { useEffect, useState } from 'react';
import { getOrchestratorStatus, triggerCycle, pauseLoop, resumeLoop, stopLoop, getGuidance, setGuidance, type OrchestratorStatus } from '../api';
import type { WSMessage } from '../hooks/useWebSocket';

const STEP_LABELS: Record<string, string> = {
  evaluate: 'Evaluating',
  propose: 'Proposing',
  branch: 'Branching',
  code: 'Coding',
  review: 'Reviewing',
  test: 'Testing',
  merge: 'Merging',
  verify: 'Verifying',
  record: 'Recording',
};

const AGENT_COLORS: Record<string, string> = {
  planner: 'text-purple-400',
  coder: 'text-blue-400',
  reviewer: 'text-yellow-400',
  tester: 'text-green-400',
  deployer: 'text-orange-400',
};

interface Props {
  ws: { messages: WSMessage[]; connected: boolean; clearMessages: () => void };
}

export default function ActivityFeed({ ws }: Props) {
  const [status, setStatus] = useState<OrchestratorStatus | null>(null);
  const [guidance, setGuidanceText] = useState('');
  const [guidanceSaved, setGuidanceSaved] = useState(false);

  useEffect(() => {
    getOrchestratorStatus().then(setStatus).catch(() => {});
    getGuidance().then((r) => setGuidanceText(r.message || '')).catch(() => {});
    const interval = setInterval(() => {
      getOrchestratorStatus().then(setStatus).catch(() => {});
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  // Update status from WS messages
  useEffect(() => {
    const latest = ws.messages[ws.messages.length - 1];
    if (latest?.type === 'system' || latest?.type === 'step' || latest?.type === 'cycle') {
      getOrchestratorStatus().then(setStatus).catch(() => {});
    }
  }, [ws.messages]);

  const handleTrigger = async () => {
    await triggerCycle();
    getOrchestratorStatus().then(setStatus);
  };

  return (
    <div className="space-y-6">
      {/* Status banner */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`w-3 h-3 rounded-full ${
              status?.running && !status?.paused ? 'bg-green-500 animate-pulse' :
              status?.paused ? 'bg-yellow-500' : 'bg-gray-600'
            }`} />
            <span className="text-sm font-medium">
              {status?.stopped ? 'Stopped' :
               status?.paused ? 'Paused' :
               status?.running ? 'Running' : 'Idle'}
            </span>
            {status?.current_step && (
              <span className="text-sm text-gray-400">
                Step: <span className="text-white">{STEP_LABELS[status.current_step] || status.current_step}</span>
              </span>
            )}
            {status?.current_cycle_id && (
              <span className="text-xs text-gray-500 font-mono">{status.current_cycle_id}</span>
            )}
          </div>
          <div className="flex gap-2">
            <button onClick={handleTrigger}
              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded text-sm transition-colors">
              Trigger Cycle
            </button>
            {status?.paused ? (
              <button onClick={() => resumeLoop().then(() => getOrchestratorStatus().then(setStatus))}
                className="px-3 py-1.5 bg-green-600 hover:bg-green-700 rounded text-sm transition-colors">
                Resume
              </button>
            ) : (
              <button onClick={() => pauseLoop().then(() => getOrchestratorStatus().then(setStatus))}
                className="px-3 py-1.5 bg-yellow-600 hover:bg-yellow-700 rounded text-sm transition-colors">
                Pause
              </button>
            )}
            <button onClick={() => stopLoop().then(() => getOrchestratorStatus().then(setStatus))}
              className="px-3 py-1.5 bg-red-600 hover:bg-red-700 rounded text-sm transition-colors">
              Stop
            </button>
          </div>
        </div>
      </div>

      {/* Guidance box */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
        <h3 className="text-sm font-medium text-gray-400 mb-2">Guide the Agents</h3>
        <p className="text-xs text-gray-600 mb-2">This message is shown to the Planner at the start of every cycle as top priority.</p>
        <div className="flex gap-2">
          <textarea
            value={guidance}
            onChange={(e) => { setGuidanceText(e.target.value); setGuidanceSaved(false); }}
            placeholder="e.g. Focus on improving error handling in the orchestrator..."
            rows={2}
            className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm text-gray-200 placeholder-gray-600 resize-none"
          />
          <button
            onClick={async () => {
              await setGuidance(guidance);
              setGuidanceSaved(true);
              setTimeout(() => setGuidanceSaved(false), 3000);
            }}
            className={`px-4 self-end rounded text-sm font-medium transition-all h-9 ${
              guidanceSaved
                ? 'bg-green-600 text-white'
                : 'bg-blue-600 hover:bg-blue-700 text-white'
            }`}
          >
            {guidanceSaved ? 'Saved' : 'Send'}
          </button>
        </div>
      </div>

      {/* Live log */}
      <div className="bg-gray-900 rounded-lg border border-gray-800">
        <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
          <h2 className="text-sm font-medium">Live Activity</h2>
          <button onClick={ws.clearMessages}
            className="text-xs text-gray-500 hover:text-gray-300">Clear</button>
        </div>
        <div className="p-4 font-mono text-xs max-h-[600px] overflow-y-auto space-y-1">
          {ws.messages.length === 0 && (
            <p className="text-gray-600">Waiting for activity...</p>
          )}
          {ws.messages.map((msg, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-gray-600 select-none w-8 text-right shrink-0">{i + 1}</span>
              {typeof msg.agent === 'string' && (
                <span className={`${AGENT_COLORS[msg.agent] || 'text-gray-400'} w-20 shrink-0`}>
                  [{msg.agent}]
                </span>
              )}
              <span className="text-gray-300">
                {msg.type === 'step' && `${msg.action} ${msg.step || ''}`}
                {msg.type === 'cycle' && `Cycle ${msg.action} ${msg.status || ''}`}
                {msg.type === 'system' && `System ${msg.action}`}
                {msg.type === 'error' && <span className="text-red-400">Error: {String(msg.message)}</span>}
                {msg.type === 'feedback' && `Feedback: ${msg.rating}`}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
