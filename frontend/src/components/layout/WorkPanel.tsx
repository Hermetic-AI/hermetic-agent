// WorkPanel — right-side panel showing tool/agent activity for the active
// turn.  Tabs: Activity / Files / Plan.  All tabs read from the same
// TraceEvent list — live-streamed during a turn or fetched via usePastTrace.

import { useState } from 'react';
import type { TraceEvent } from '../../hooks/useWorkPanel';
import { ActivityFeed } from '../work/ActivityFeed';
import { FilesTab } from '../work/FilesTab';
import { PlanTab } from '../work/PlanTab';
import './WorkPanel.css';

export type WorkTab = 'activity' | 'files' | 'plan';

export interface WorkPanelProps {
  events: TraceEvent[];
  defaultTab?: WorkTab;
}

export function WorkPanel({ events, defaultTab = 'activity' }: WorkPanelProps) {
  const [tab, setTab] = useState<WorkTab>(defaultTab);
  return (
    <aside className="work-panel">
      <div className="work-panel-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-pressed={tab === 'activity'}
          className={`work-panel-tab ${tab === 'activity' ? 'is-active' : ''}`}
          onClick={() => setTab('activity')}
        >
          Activity <span className="work-panel-count">{events.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-pressed={tab === 'files'}
          className={`work-panel-tab ${tab === 'files' ? 'is-active' : ''}`}
          onClick={() => setTab('files')}
        >
          Files
        </button>
        <button
          type="button"
          role="tab"
          aria-pressed={tab === 'plan'}
          className={`work-panel-tab ${tab === 'plan' ? 'is-active' : ''}`}
          onClick={() => setTab('plan')}
        >
          Plan
        </button>
      </div>
      <div className="work-panel-body">
        {tab === 'activity' && <ActivityFeed events={events} />}
        {tab === 'files' && <FilesTab events={events} />}
        {tab === 'plan' && <PlanTab events={events} />}
      </div>
    </aside>
  );
}