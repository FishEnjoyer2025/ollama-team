import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { useWebSocket } from './hooks/useWebSocket';
import ActivityFeed from './pages/ActivityFeed';
import CycleHistory from './pages/CycleHistory';
import AgentProfiles from './pages/AgentProfiles';
import SystemHealth from './pages/SystemHealth';
import Settings from './pages/Settings';

const navItems = [
  { to: '/', label: 'Activity' },
  { to: '/cycles', label: 'Cycles' },
  { to: '/agents', label: 'Agents' },
  { to: '/health', label: 'Health' },
  { to: '/settings', label: 'Settings' },
];

export default function App() {
  const ws = useWebSocket();

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-gray-100">
        <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-50">
          <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-6">
            <h1 className="text-lg font-semibold text-white tracking-tight">
              Ollama Team
            </h1>
            <div className={`w-2 h-2 rounded-full ${ws.connected ? 'bg-green-500' : 'bg-red-500'}`}
                 title={ws.connected ? 'Connected' : 'Disconnected'} />
            <nav className="flex gap-1 ml-4">
              {navItems.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === '/'}
                  className={({ isActive }) =>
                    `px-3 py-1.5 rounded text-sm transition-colors ${
                      isActive
                        ? 'bg-blue-600 text-white'
                        : 'text-gray-400 hover:text-white hover:bg-gray-800'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        </header>

        <main className="max-w-7xl mx-auto px-4 py-6">
          <Routes>
            <Route path="/" element={<ActivityFeed ws={ws} />} />
            <Route path="/cycles" element={<CycleHistory />} />
            <Route path="/agents" element={<AgentProfiles />} />
            <Route path="/health" element={<SystemHealth />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
