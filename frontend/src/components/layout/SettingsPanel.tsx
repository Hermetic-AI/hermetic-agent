import { useState } from 'react';
import { Modal, Skeleton, Empty, Badge } from '../common';
import { useSkills, useTools, usePool, useHealth } from '../../hooks';
import type { Tool } from '../../types';
import './SettingsPanel.css';

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

type Tab = 'overview' | 'skills' | 'tools' | 'agents';

export function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  const [tab, setTab] = useState<Tab>('overview');
  const { state, detail, ready } = useHealth();
  return (
    <Modal open={open} onClose={onClose} title="设置" size="large">
      <div className="settings-panel">
        <div className="settings-tabs">
          <SettingsTab id="overview" label="概览" current={tab} onSelect={setTab} />
          <SettingsTab id="skills" label="技能" current={tab} onSelect={setTab} />
          <SettingsTab id="tools" label="工具" current={tab} onSelect={setTab} />
          <SettingsTab id="agents" label="Agent" current={tab} onSelect={setTab} />
        </div>
        <div className="settings-body">
          {tab === 'overview' && (
            <Overview state={state} detail={detail} ready={ready} />
          )}
          {tab === 'skills' && <SkillsTab />}
          {tab === 'tools' && <ToolsTab />}
          {tab === 'agents' && <AgentsTab />}
        </div>
      </div>
    </Modal>
  );
}

function SettingsTab({
  id,
  label,
  current,
  onSelect,
}: {
  id: Tab;
  label: string;
  current: Tab;
  onSelect: (t: Tab) => void;
}) {
  return (
    <button
      type="button"
      className={`settings-tab ${current === id ? 'settings-tab-active' : ''}`}
      onClick={() => onSelect(id)}
    >
      {label}
    </button>
  );
}

function Overview({
  state,
  detail,
  ready,
}: {
  state: ReturnType<typeof useHealth>['state'];
  detail: string | null;
  ready: ReturnType<typeof useHealth>['ready'];
}) {
  return (
    <div className="settings-overview">
      <Row label="后端状态">
        <Badge variant={state === 'healthy' ? 'success' : state === 'degraded' ? 'warning' : 'danger'}>
          {state}
        </Badge>
        {detail && <span className="settings-muted">{detail}</span>}
      </Row>
      <Row label="存储">{ready?.storage ? '已连接' : '未就绪'}</Row>
      <Row label="Agent 桥接">{ready?.bridge ? '已就绪' : '未就绪'}</Row>
      <Row label="技能">{ready?.skills_count ?? 0} 项</Row>
      <Row label="工具">{ready?.tools_count ?? 0} 项</Row>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="settings-row">
      <span className="settings-label">{label}</span>
      <span className="settings-value">{children}</span>
    </div>
  );
}

function SkillsTab() {
  const { skills, loading, error } = useSkills();
  if (loading) return <SkeletonList />;
  if (error) return <Empty title="加载失败" description={error} />;
  if (skills.length === 0) return <Empty title="暂未注册技能" description="通过后端加载 SKILL.md 目录或调用 POST /agent/skills 注册。" />;
  return (
    <ul className="settings-list">
      {skills.map((s) => (
        <li key={s.name} className="settings-card">
          <div className="settings-card-head">
            <strong>{s.name}</strong>
            <span className="settings-muted">v{s.version}</span>
          </div>
          <p className="settings-card-desc">{s.description || '—'}</p>
          {s.triggers.length > 0 && (
            <div className="settings-triggers">
              {s.triggers.map((t) => (
                <Badge key={t} variant="info">{t}</Badge>
              ))}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function ToolsTab() {
  const { tools, loading, error, setEnabled } = useTools();
  const [busy, setBusy] = useState<string | null>(null);
  if (loading) return <SkeletonList />;
  if (error) return <Empty title="加载失败" description={error} />;
  if (tools.length === 0) return <Empty title="暂未注册工具" description="调用 POST /agent/tools 注册 MCP 工具。" />;
  return (
    <ul className="settings-list">
      {tools.map((t) => (
        <ToolRow
          key={t.name}
          tool={t}
          busy={busy === t.name}
          onToggle={async (enabled) => {
            setBusy(t.name);
            try {
              await setEnabled(t.name, enabled);
            } finally {
              setBusy(null);
            }
          }}
        />
      ))}
    </ul>
  );
}

function ToolRow({
  tool,
  busy,
  onToggle,
}: {
  tool: Tool;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
}) {
  return (
    <li className="settings-card">
      <div className="settings-card-head">
        <strong>{tool.name}</strong>
        <label className="settings-switch">
          <input
            type="checkbox"
            checked={tool.enabled}
            disabled={busy}
            onChange={(e) => onToggle(e.target.checked)}
          />
          <span>{tool.enabled ? '已启用' : '已禁用'}</span>
        </label>
      </div>
      <p className="settings-card-desc">{tool.description || '—'}</p>
      <div className="settings-card-meta">
        <Badge variant={tool.source === 'remote' ? 'warning' : 'default'}>
          {tool.source ?? 'local'}
        </Badge>
        {tool.remote_url && <span className="settings-muted">{tool.remote_url}</span>}
      </div>
    </li>
  );
}

function AgentsTab() {
  const { stats, loading, error } = usePool();
  if (loading) return <SkeletonList />;
  if (error) return <Empty title="加载失败" description={error} />;
  if (!stats || stats.total_agents === 0) {
    return (
      <Empty
        title="暂无已注册 Agent"
        description="通过 POST /agent/pool/register 注册 OpenCode/Claude Code 实例。"
      />
    );
  }
  return (
    <ul className="settings-list">
      {Object.values(stats.agents).map((a) => (
        <li key={a.name} className="settings-card">
          <div className="settings-card-head">
            <strong>{a.name}</strong>
            <Badge variant="info">{a.sdk_type}</Badge>
          </div>
          <div className="settings-card-meta">
            <span className="settings-muted">{a.base_url}</span>
            {a.default_model && <span className="settings-muted">默认模型: {a.default_model}</span>}
          </div>
        </li>
      ))}
    </ul>
  );
}

function SkeletonList() {
  return (
    <ul className="settings-list">
      {[0, 1, 2].map((i) => (
        <li key={i} className="settings-card">
          <Skeleton width="40%" height={18} />
          <Skeleton width="80%" height={14} />
        </li>
      ))}
    </ul>
  );
}
