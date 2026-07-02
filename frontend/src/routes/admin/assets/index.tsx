import { useState } from 'react';
import { SkillsTab } from './tabs/SkillsTab';
import { McpsTab } from './tabs/McpsTab';
import { PromptsTab } from './tabs/PromptsTab';
import { CommandsTab } from './tabs/CommandsTab';
import { AgentsTab } from './tabs/AgentsTab';
import './index.css';

type TabId = 'skills' | 'mcps' | 'prompts' | 'commands' | 'agents';

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'skills', label: 'Skills' },
  { id: 'mcps', label: 'MCPs' },
  { id: 'prompts', label: 'Prompts' },
  { id: 'commands', label: 'Commands' },
  { id: 'agents', label: 'Agents' },
];

export function AssetsPage() {
  const [activeTab, setActiveTab] = useState<TabId>('skills');

  return (
    <div className="admin-assets-page">
      <div className="assets-page-header">
        <h1>Assets Registry</h1>
        <p className="assets-page-subtitle">
          Manage the registry of reusable resources available to agents.
        </p>
      </div>
      <div className="assets-tabs" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`assets-tab-button ${activeTab === tab.id ? 'is-active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="assets-tab-panel" role="tabpanel">
        {activeTab === 'skills' && <SkillsTab />}
        {activeTab === 'mcps' && <McpsTab />}
        {activeTab === 'prompts' && <PromptsTab />}
        {activeTab === 'commands' && <CommandsTab />}
        {activeTab === 'agents' && <AgentsTab />}
      </div>
    </div>
  );
}
