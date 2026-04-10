import { useEffect, useState } from 'react';
import { getCycles, submitFeedback, type Cycle } from '../api';

const STATUS_COLORS: Record<string, string> = {
  success: 'bg-green-500/20 text-green-400 border-green-500/30',
  failed: 'bg-red-500/20 text-red-400 border-red-500/30',
  rolled_back: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  abandoned: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  running: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
};

export default function CycleHistory() {
  const [cycles, setCycles] = useState<Cycle[]>([]);
  const [filter, setFilter] = useState<string>('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [noteInputs, setNoteInputs] = useState<Record<string, string>>({});

  const load = () => {
    getCycles({ status: filter || undefined, limit: 50 })
      .then((r) => setCycles(r.cycles))
      .catch(() => {});
  };

  useEffect(load, [filter]);

  const handleFeedback = async (cycleId: string, rating: 'up' | 'down') => {
    const note = noteInputs[cycleId] || undefined;
    await submitFeedback(cycleId, rating, note);
    setNoteInputs((prev) => ({ ...prev, [cycleId]: '' }));
    load();
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">Improvement Cycles</h2>
        <div className="flex gap-2">
          {['', 'success', 'failed', 'rolled_back', 'abandoned'].map((f) => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-2 py-1 rounded text-xs transition-colors ${
                filter === f ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
              }`}>
              {f || 'All'}
            </button>
          ))}
        </div>
      </div>

      {cycles.length === 0 && (
        <p className="text-gray-600 text-center py-12">No cycles yet. The agents haven't started improving themselves.</p>
      )}

      <div className="space-y-2">
        {cycles.map((cycle) => (
          <div key={cycle.id} className="bg-gray-900 rounded-lg border border-gray-800">
            {/* Summary row */}
            <button
              onClick={() => setExpanded(expanded === cycle.id ? null : cycle.id)}
              className="w-full px-4 py-3 flex items-center gap-4 text-left hover:bg-gray-800/50 transition-colors"
            >
              <span className="font-mono text-xs text-gray-500 w-16 shrink-0">{cycle.id}</span>
              <span className={`px-2 py-0.5 rounded-full text-xs border ${STATUS_COLORS[cycle.status] || ''}`}>
                {cycle.status}
              </span>
              <span className="text-sm text-gray-300 truncate flex-1">
                {typeof cycle.proposal === 'object' && cycle.proposal
                  ? cycle.proposal.description
                  : 'No description'}
              </span>
              <span className="text-xs text-gray-600 shrink-0">
                {cycle.started_at ? new Date(cycle.started_at).toLocaleString() : ''}
              </span>
            </button>

            {/* Expanded details */}
            {expanded === cycle.id && (
              <div className="px-4 pb-4 border-t border-gray-800 space-y-3">
                {typeof cycle.proposal === 'object' && cycle.proposal && (
                  <div className="mt-3">
                    <h4 className="text-xs text-gray-500 uppercase tracking-wider mb-1">Proposal</h4>
                    <p className="text-sm text-gray-300">{cycle.proposal.description}</p>
                    <p className="text-xs text-gray-500 mt-1">
                      Files: {cycle.proposal.files?.join(', ') || 'none'} | Risk: {cycle.proposal.risk}
                    </p>
                    <p className="text-xs text-gray-500">
                      Expected: {cycle.proposal.expected_outcome}
                    </p>
                  </div>
                )}

                {cycle.diff && (
                  <div>
                    <h4 className="text-xs text-gray-500 uppercase tracking-wider mb-1">Diff</h4>
                    <pre className="bg-gray-950 rounded p-3 text-xs overflow-x-auto max-h-64 overflow-y-auto">
                      {cycle.diff}
                    </pre>
                  </div>
                )}

                {cycle.test_output && (
                  <div>
                    <h4 className="text-xs text-gray-500 uppercase tracking-wider mb-1">Test Output</h4>
                    <pre className="bg-gray-950 rounded p-3 text-xs overflow-x-auto max-h-40 overflow-y-auto">
                      {cycle.test_output}
                    </pre>
                  </div>
                )}

                {cycle.rollback_reason && (
                  <div>
                    <h4 className="text-xs text-red-500 uppercase tracking-wider mb-1">Rollback Reason</h4>
                    <p className="text-sm text-red-300">{cycle.rollback_reason}</p>
                  </div>
                )}

                {/* Feedback */}
                <div className="flex items-center gap-3 pt-2 border-t border-gray-800">
                  <span className="text-xs text-gray-500">Rate this cycle:</span>
                  <button onClick={() => handleFeedback(cycle.id, 'up')}
                    className="px-3 py-1 bg-green-900/40 hover:bg-green-800/60 text-green-400 rounded text-sm transition-colors">
                    Thumbs Up
                  </button>
                  <button onClick={() => handleFeedback(cycle.id, 'down')}
                    className="px-3 py-1 bg-red-900/40 hover:bg-red-800/60 text-red-400 rounded text-sm transition-colors">
                    Thumbs Down
                  </button>
                  <input
                    type="text"
                    placeholder="Optional note..."
                    value={noteInputs[cycle.id] || ''}
                    onChange={(e) => setNoteInputs((prev) => ({ ...prev, [cycle.id]: e.target.value }))}
                    className="flex-1 px-2 py-1 bg-gray-800 border border-gray-700 rounded text-sm text-gray-300 placeholder-gray-600"
                  />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
