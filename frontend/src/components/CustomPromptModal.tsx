typescript
import { useState } from 'react';
import { updateAgentPrompt } from '../api';

interface CustomPromptModalProps {
  agentName: string;
  onClose: () => void;
}

const CustomPromptModal: React.FC<CustomPromptModalProps> = ({ agentName, onClose }) => {
  const [prompt, setPrompt] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await updateAgentPrompt(agentName, prompt);
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
      <div className="bg-white p-6 rounded-lg shadow-lg w-96">
        <h2 className="text-xl font-bold mb-4">Custom Prompt for {agentName}</h2>
        <form onSubmit={handleSubmit}>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={5}
            className="w-full border rounded p-2"
            placeholder="Enter custom prompt here..."
          />
          <div className="flex justify-end mt-4">
            <button type="submit" className="bg-blue-500 text-white px-4 py-2 rounded hover:bg-blue-600">
              Save
            </button>
            <button type="button" onClick={onClose} className="ml-2 bg-gray-300 text-gray-700 px-4 py-2 rounded hover:bg-gray-400">
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CustomPromptModal;