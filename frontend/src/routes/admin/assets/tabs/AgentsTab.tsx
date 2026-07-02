import { useEffect, useState, useCallback } from 'react';
import { Button } from '../../../components/common/Button';
import { Card, CardBody, CardFooter, CardHeader } from '../../../components/common/Card';
import { Empty } from '../../../components/common/Empty';
import { Modal, ConfirmModal } from '../../../components/common/Modal';
import { Skeleton } from '../../../components/common/Skeleton';
import { Input } from '../../../components/common/Input';
import { Badge } from '../../../components/common/Badge';
import { MultiSelectPicker, type MultiSelectOption } from '../../../components/common/MultiSelectPicker';
import { agentsApi } from '../../../services/agents';
import { promptsApi } from '../../../services/prompts';
import { commandsApi } from '../../../services/commands';
import { mcpConfigsApi } from '../../../services/mcp_configs';
import { skillsApi } from '../../../services/skills';
import type { AgentAsset } from '../../../types/assets';
import '../index.css';
import './AgentsTab.css';

type ToolLevel = AgentAsset['tool_level'];
type NetworkMode = AgentAsset['network'];
type AssetStatus = AgentAsset['status'];
type Visibility = AgentAsset['visibility'];

interface AgentForm {
  code: string;
  name: string;
  description: string;
  system_prompt: string;
  model: string;
  tool_level: ToolLevel;
  network: NetworkMode;
  status: AssetStatus;
  skill_codes: string[];
  mcp_server_codes: string[];
  prompt_codes: string[];
  command_codes: string[];
}

const NEW_AGENT: AgentForm = {
  code: '',
  name: '',
  description: '',
  system_prompt: '',
  model: 'openai/gpt-4o-mini',
  tool_level: 'standard',
  network: 'local',
  status: 'draft',
  skill_codes: [],
  mcp_server_codes: [],
  prompt_codes: [],
  command_codes: [],
};

const CODE_RE = /^[A-Za-z0-9_.-]+$/;

interface PickerOptions {
  prompts: MultiSelectOption[];
  commands: MultiSelectOption[];
  mcps: MultiSelectOption[];
  skills: MultiSelectOption[];
}

const EMPTY_PICKERS: PickerOptions = {
  prompts: [],
  commands: [],
  mcps: [],
  skills: [],
};

export function AgentsTab() {
  const [items, setItems] = useState<AgentAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<AgentForm | null>(null);
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<AgentAsset | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickerOptions, setPickerOptions] = useState<PickerOptions>(EMPTY_PICKERS);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [togglingPublish, setTogglingPublish] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const r = await agentsApi.list();
      setItems(r.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  const loadPickerOptions = useCallback(async () => {
    setPickerLoading(true);
    try {
      const results = await Promise.allSettled([
        promptsApi.list({ limit: 200 }),
        commandsApi.list({ limit: 200 }),
        mcpConfigsApi.list({ limit: 200 }),
        skillsApi.list({ limit: 200 }),
      ]);
      setPickerOptions((prev) => ({
        prompts:
          results[0].status === 'fulfilled'
            ? results[0].value.items.map((p) => ({ value: p.code, label: `${p.code} — ${p.name}` }))
            : prev.prompts,
        commands:
          results[1].status === 'fulfilled'
            ? results[1].value.items.map((c) => ({ value: c.code, label: `${c.code} — ${c.name}` }))
            : prev.commands,
        mcps:
          results[2].status === 'fulfilled'
            ? results[2].value.items.map((m) => ({ value: m.code, label: `${m.code} — ${m.name}` }))
            : prev.mcps,
        skills:
          results[3].status === 'fulfilled'
            ? results[3].value.skills.map((s) => ({ value: s.code, label: `${s.code} — ${s.name}` }))
            : prev.skills,
      }));
      const errors = results
        .map((r, i) =>
          r.status === 'rejected'
            ? `resource ${i}: ${r.reason instanceof Error ? r.reason.message : String(r.reason)}`
            : null,
        )
        .filter((e): e is string => e !== null);
      if (errors.length) setError(`Some resources failed to load: ${errors.join('; ')}`);
    } finally {
      setPickerLoading(false);
    }
  }, []);

  function openNew() {
    setEditing({ ...NEW_AGENT });
    setEditingCode(null);
    setError(null);
    loadPickerOptions();
  }

  function openEdit(item: AgentAsset) {
    setEditing({
      code: item.code,
      name: item.name,
      description: item.description ?? '',
      system_prompt: item.system_prompt,
      model: item.model,
      tool_level: item.tool_level,
      network: item.network,
      status: item.status,
      skill_codes: [...item.skill_codes],
      mcp_server_codes: [...item.mcp_server_codes],
      prompt_codes: [...item.prompt_codes],
      command_codes: [...item.command_codes],
    });
    setEditingCode(item.code);
    setError(null);
    loadPickerOptions();
  }

  async function handleSave() {
    if (!editing) return;
    if (!editing.code.trim() || !editing.name.trim()) {
      setError('Code and Name are required');
      return;
    }
    if (!CODE_RE.test(editing.code)) {
      setError('Code must match [A-Za-z0-9_.-]+');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (editingCode) {
        await agentsApi.update(editingCode, {
          name: editing.name,
          description: editing.description || null,
          system_prompt: editing.system_prompt,
          model: editing.model,
          tool_level: editing.tool_level,
          network: editing.network,
          status: editing.status,
          skill_codes: editing.skill_codes,
          mcp_server_codes: editing.mcp_server_codes,
          prompt_codes: editing.prompt_codes,
          command_codes: editing.command_codes,
        });
      } else {
        await agentsApi.create({
          code: editing.code,
          name: editing.name,
          description: editing.description || null,
          system_prompt: editing.system_prompt,
          model: editing.model,
          tool_level: editing.tool_level,
          network: editing.network,
          status: editing.status,
          skill_codes: editing.skill_codes,
          mcp_server_codes: editing.mcp_server_codes,
          prompt_codes: editing.prompt_codes,
          command_codes: editing.command_codes,
        });
      }
      setEditing(null);
      setEditingCode(null);
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    setSaving(true);
    try {
      await agentsApi.delete(deleting.code);
      setDeleting(null);
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleTogglePublish(item: AgentAsset) {
    const next: Visibility = item.visibility === 'public' ? 'private' : 'public';
    setTogglingPublish(item.code);
    try {
      await agentsApi.publish(item.code, next);
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTogglingPublish(null);
    }
  }

  return (
    <div className="assets-tab">
      <div className="assets-tab-header">
        <h2>Agents ({items.length})</h2>
        <Button variant="primary" onClick={openNew}>+ New Agent</Button>
      </div>
      {error && <p className="asset-form-error">{error}</p>}
      {loading ? <Skeleton variant="rectangular" height={120} /> :
       items.length === 0 ? (
         <Empty
           title="No agents yet"
           description="Compose an agent from skills, MCP servers, prompts, and commands."
           action={{ label: 'Create first', onClick: openNew }}
         />
       ) : (
         <div className="assets-tab-grid">
           {items.map((item) => (
             <Card key={item.code}>
               <CardHeader>
                 <div className="agent-card-title">
                   <strong>{item.name}</strong>
                   <Badge variant={item.visibility === 'public' ? 'info' : 'default'}>
                     {item.visibility}
                   </Badge>
                   <span className={`asset-status-badge asset-status-${item.status}`}>{item.status}</span>
                 </div>
               </CardHeader>
               <CardBody>
                 <div className="asset-card-meta">
                   <div className="asset-card-meta-item">
                     <span className="asset-card-meta-label">Code:</span>
                     <span>{item.code}</span>
                   </div>
                   {item.description && (
                     <div className="asset-card-meta-item">
                       <span className="asset-card-meta-label">Desc:</span>
                       <span>{item.description}</span>
                     </div>
                   )}
                   <div className="asset-card-meta-item">
                     <span className="asset-card-meta-label">Model:</span>
                     <span>{item.model}</span>
                   </div>
                   <div className="asset-card-meta-item">
                     <span className="asset-card-meta-label">Tooling:</span>
                     <span>{item.tool_level} · {item.network}</span>
                   </div>
                 </div>
                 <div className="agent-ref-counts">
                   <Badge variant="default">skills: {item.skill_codes.length}</Badge>
                   <Badge variant="default">mcps: {item.mcp_server_codes.length}</Badge>
                   <Badge variant="default">prompts: {item.prompt_codes.length}</Badge>
                   <Badge variant="default">commands: {item.command_codes.length}</Badge>
                 </div>
               </CardBody>
               <CardFooter>
                 <div className="asset-card-row">
                   <Button size="small" onClick={() => openEdit(item)}>Edit</Button>
                   <Button
                     size="small"
                     variant="secondary"
                     onClick={() => handleTogglePublish(item)}
                     loading={togglingPublish === item.code}
                   >
                     {item.visibility === 'public' ? 'Make private' : 'Make public'}
                   </Button>
                   <Button size="small" variant="danger" onClick={() => setDeleting(item)}>Delete</Button>
                 </div>
               </CardFooter>
             </Card>
           ))}
         </div>
       )}
      {editing && (
        <AgentEditDialog
          item={editing}
          isNew={editingCode === null}
          saving={saving}
          error={error}
          pickers={pickerOptions}
          pickersLoading={pickerLoading}
          onChange={setEditing}
          onSave={handleSave}
          onClose={() => { setEditing(null); setEditingCode(null); setError(null); }}
        />
      )}
      {deleting && (
        <ConfirmModal
          open
          onClose={() => setDeleting(null)}
          onConfirm={handleDelete}
          title="Delete agent"
          message={`Delete agent ${deleting.code}? This cannot be undone.`}
          confirmText="Delete"
          variant="danger"
        />
      )}
    </div>
  );
}

interface AgentEditDialogProps {
  item: AgentForm;
  isNew: boolean;
  saving: boolean;
  error: string | null;
  pickers: PickerOptions;
  pickersLoading: boolean;
  onChange: (next: AgentForm) => void;
  onSave: () => void;
  onClose: () => void;
}

function AgentEditDialog({
  item,
  isNew,
  saving,
  error,
  pickers,
  pickersLoading,
  onChange,
  onSave,
  onClose,
}: AgentEditDialogProps) {
  return (
    <Modal
      open
      onClose={onClose}
      title={isNew ? 'New Agent' : `Edit Agent: ${item.code}`}
      size="large"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button variant="primary" onClick={onSave} loading={saving}>Save</Button>
        </>
      }
    >
      <div className="asset-form">
        <fieldset className="agent-form-section">
          <legend>Identity</legend>
          <div className="asset-form-row">
            <Input
              label="Code"
              value={item.code}
              disabled={!isNew}
              onChange={(e) => onChange({ ...item, code: e.target.value })}
              placeholder="my-agent"
            />
            <Input
              label="Name"
              value={item.name}
              onChange={(e) => onChange({ ...item, name: e.target.value })}
              placeholder="My Agent"
            />
          </div>
          <Input
            label="Description"
            value={item.description}
            onChange={(e) => onChange({ ...item, description: e.target.value })}
            placeholder="Short description"
          />
        </fieldset>

        <fieldset className="agent-form-section">
          <legend>System</legend>
          <label>
            <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>
              System Prompt
            </span>
            <textarea
              className="asset-form-textarea"
              value={item.system_prompt}
              onChange={(e) => onChange({ ...item, system_prompt: e.target.value })}
              placeholder="You are a helpful agent..."
            />
          </label>
          <div className="asset-form-row">
            <Input
              label="Model"
              value={item.model}
              onChange={(e) => onChange({ ...item, model: e.target.value })}
              placeholder="openai/gpt-4o-mini"
            />
            <div className="agent-form-select">
              <label className="agent-form-select-label">Tool Level</label>
              <select
                value={item.tool_level}
                onChange={(e) => onChange({ ...item, tool_level: e.target.value as ToolLevel })}
              >
                <option value="safe">safe</option>
                <option value="standard">standard</option>
                <option value="full">full</option>
              </select>
            </div>
            <div className="agent-form-select">
              <label className="agent-form-select-label">Network</label>
              <select
                value={item.network}
                onChange={(e) => onChange({ ...item, network: e.target.value as NetworkMode })}
              >
                <option value="off">off</option>
                <option value="local">local</option>
                <option value="any">any</option>
              </select>
            </div>
            <div className="agent-form-select">
              <label className="agent-form-select-label">Status</label>
              <select
                value={item.status}
                onChange={(e) => onChange({ ...item, status: e.target.value as AssetStatus })}
              >
                <option value="enabled">enabled</option>
                <option value="disabled">disabled</option>
                <option value="draft">draft</option>
              </select>
            </div>
          </div>
        </fieldset>

        <fieldset className="agent-form-section">
          <legend>References</legend>
          {pickersLoading ? (
            <p className="asset-form-help">Loading available resources...</p>
          ) : (
            <div className="agent-pickers-grid">
              <MultiSelectPicker
                label="Skills"
                options={pickers.skills}
                value={item.skill_codes}
                onChange={(next) => onChange({ ...item, skill_codes: next })}
                emptyMessage="No skills available — create one first"
                placeholder="No skills selected"
                disabled={saving}
                testId="picker-skills"
              />
              <MultiSelectPicker
                label="MCP Servers"
                options={pickers.mcps}
                value={item.mcp_server_codes}
                onChange={(next) => onChange({ ...item, mcp_server_codes: next })}
                emptyMessage="No MCP servers available"
                placeholder="No MCP servers selected"
                disabled={saving}
                testId="picker-mcps"
              />
              <MultiSelectPicker
                label="Prompts"
                options={pickers.prompts}
                value={item.prompt_codes}
                onChange={(next) => onChange({ ...item, prompt_codes: next })}
                emptyMessage="No prompts available"
                placeholder="No prompts selected"
                disabled={saving}
                testId="picker-prompts"
              />
              <MultiSelectPicker
                label="Commands"
                options={pickers.commands}
                value={item.command_codes}
                onChange={(next) => onChange({ ...item, command_codes: next })}
                emptyMessage="No commands available"
                placeholder="No commands selected"
                disabled={saving}
                testId="picker-commands"
              />
            </div>
          )}
        </fieldset>

        {error && <p className="asset-form-error">{error}</p>}
      </div>
    </Modal>
  );
}
