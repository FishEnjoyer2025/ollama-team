import { useEffect, useState } from 'react';
import { getSettings, updateSettings } from '../api';

interface SettingField {
  key: string;
  label: string;
  type: 'number' | 'boolean';
  description: string;
}

const FIELDS: SettingField[] = [
  { key: 'cycle_cooldown_seconds', label: 'Cycle Cooldown', type: 'number', description: 'Seconds between improvement cycles' },
  { key: 'max_retries_per_step', label: 'Max Retries', type: 'number', description: 'Max retry attempts per pipeline step' },
  { key: 'process_timeout_seconds', label: 'Process Timeout', type: 'number', description: 'Max seconds per agent invocation' },
  { key: 'health_check_timeout_seconds', label: 'Health Check Timeout', type: 'number', description: 'Seconds to wait for health check' },
  { key: 'paused', label: 'Paused', type: 'boolean', description: 'Pause the improvement loop' },
  { key: 'stopped', label: 'Stopped', type: 'boolean', description: 'Stop the improvement loop entirely' },
];

export default function Settings() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getSettings().then(setSettings).catch(() => {});
  }, []);

  const handleChange = (key: string, value: string) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updates: Record<string, string | number | boolean> = {};
      for (const field of FIELDS) {
        const val = settings[field.key];
        if (val !== undefined) {
          if (field.type === 'number') updates[field.key] = parseInt(val, 10);
          else if (field.type === 'boolean') updates[field.key] = val === 'true';
        }
      }
      const result = await updateSettings(updates);
      setSettings(result);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <h2 className="text-lg font-medium">Settings</h2>

      <div className="space-y-4">
        {FIELDS.map((field) => (
          <div key={field.key} className="bg-gray-900 rounded-lg border border-gray-800 p-4">
            <div className="flex items-center justify-between">
              <div>
                <label className="text-sm font-medium text-white">{field.label}</label>
                <p className="text-xs text-gray-500 mt-0.5">{field.description}</p>
              </div>
              {field.type === 'number' ? (
                <input
                  type="number"
                  value={settings[field.key] || ''}
                  onChange={(e) => handleChange(field.key, e.target.value)}
                  className="w-24 px-2 py-1 bg-gray-800 border border-gray-700 rounded text-sm text-white text-right"
                />
              ) : (
                <button
                  onClick={() => handleChange(field.key, settings[field.key] === 'true' ? 'false' : 'true')}
                  className={`w-12 h-6 rounded-full transition-colors ${
                    settings[field.key] === 'true' ? 'bg-blue-600' : 'bg-gray-700'
                  }`}
                >
                  <div className={`w-5 h-5 bg-white rounded-full transition-transform mx-0.5 ${
                    settings[field.key] === 'true' ? 'translate-x-6' : ''
                  }`} />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <button onClick={handleSave} disabled={saving}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded text-sm font-medium transition-colors">
        {saving ? 'Saving...' : 'Save Settings'}
      </button>
    </div>
  );
}
