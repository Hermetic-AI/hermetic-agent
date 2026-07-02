import { useEffect, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  Empty,
  Modal,
  ConfirmModal,
  Skeleton,
  Input,
} from '../../../../components/common';
import { commandsApi } from '../../../services/commands';
import type { CommandAsset } from '../../../types/assets';
import '../index.css';
import './CommandsTab.css';

const NEW_COMMAND: Omit<CommandAsset, 'id' | 'created_at' | 'updated_at' | 'owner_user_id' | 'visibility' | 'version'> = {
  code: '',
  name: '',
  description: '',
  status: 'draft',
  slash_command: '/',
  system_prompt_addendum: '',
  enabled: true,
};

export function CommandsTab() {
  const [items, setItems] = useState<CommandAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<typeof NEW_COMMAND | null>(null);
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<CommandAsset | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { loadList(); }, []);

  async function loadList() {
    setLoading(true);
    try {
      const r = await commandsApi.list();
      setItems(r.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function openNew() {
    setEditing({ ...NEW_COMMAND });
    setEditingCode(null);
    setError(null);
  }

  function openEdit(item: CommandAsset) {
    setEditing({
      code: item.code,
      name: item.name,
      description: item.description ?? '',
      status: item.status,
      slash_command: item.slash_command,
      system_prompt_addendum: item.system_prompt_addendum,
      enabled: item.enabled,
    });
    setEditingCode(item.code);
    setError(null);
  }

  async function handleSave() {
    if (!editing) return;
    if (!editing.code.trim() || !editing.name.trim()) {
      setError('Code and Name are required');
      return;
    }
    let slash = editing.slash_command.trim();
    if (!slash.startsWith('/')) {
      slash = '/' + slash.replace(/^\/+/, '');
    }
    if (slash === '/' || slash.length < 2) {
      setError('Slash command must start with / and have at least one character after it');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = { ...editing, slash_command: slash };
      if (editingCode) {
        await commandsApi.update(editingCode, payload);
      } else {
        await commandsApi.create(payload);
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
      await commandsApi.delete(deleting.code);
      setDeleting(null);
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="assets-tab">
      <div className="assets-tab-header">
        <h2>Commands ({items.length})</h2>
        <Button variant="primary" onClick={openNew}>+ New Command</Button>
      </div>
      {error && <p className="asset-form-error">{error}</p>}
      {loading ? <Skeleton variant="rectangular" height={120} /> :
       items.length === 0 ? (
         <Empty
           title="No commands yet"
           description="Create slash-commands agents can invoke."
           action={{ label: 'Create first', onClick: openNew }}
         />
       ) : (
         <div className="assets-tab-grid">
           {items.map((item) => (
             <Card key={item.code}>
               <CardHeader>
                 <strong>{item.name}</strong>
                 <code style={{ fontSize: 12, color: '#6c6c70' }}>{item.slash_command}</code>
               </CardHeader>
               <CardBody>
                 <div className="asset-card-meta">
                   <div className="asset-card-meta-item">
                     <span className="asset-card-meta-label">Code:</span>
                     <span>{item.code}</span>
                   </div>
                   <div className="asset-card-meta-item">
                     <span className="asset-card-meta-label">Status:</span>
                     <span className={`asset-status-badge asset-status-${item.status}`}>{item.status}</span>
                   </div>
                   <div className="asset-card-meta-item">
                     <span className="asset-card-meta-label">Enabled:</span>
                     <span>{item.enabled ? 'Yes' : 'No'}</span>
                   </div>
                 </div>
               </CardBody>
               <CardFooter>
                 <div className="asset-card-row">
                   <Button size="small" onClick={() => openEdit(item)}>Edit</Button>
                   <Button size="small" variant="danger" onClick={() => setDeleting(item)}>Delete</Button>
                 </div>
               </CardFooter>
             </Card>
           ))}
         </div>
       )}
      {editing && (
        <CommandEditDialog
          item={editing}
          isNew={editingCode === null}
          saving={saving}
          error={error}
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
          title="Delete command"
          message={`Delete command ${deleting.code}? This cannot be undone.`}
          confirmText="Delete"
          variant="danger"
        />
      )}
    </div>
  );
}

interface CommandEditDialogProps {
  item: typeof NEW_COMMAND;
  isNew: boolean;
  saving: boolean;
  error: string | null;
  onChange: (next: typeof NEW_COMMAND) => void;
  onSave: () => void;
  onClose: () => void;
}

function CommandEditDialog({ item, isNew, saving, error, onChange, onSave, onClose }: CommandEditDialogProps) {
  return (
    <Modal
      open
      onClose={onClose}
      title={isNew ? 'New Command' : `Edit Command: ${item.code}`}
      size="large"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button variant="primary" onClick={onSave} loading={saving}>Save</Button>
        </>
      }
    >
      <div className="asset-form">
        <div className="asset-form-row">
          <Input
            label="Code"
            value={item.code}
            disabled={!isNew}
            onChange={(e) => onChange({ ...item, code: e.target.value })}
            placeholder="summarize"
          />
          <Input
            label="Name"
            value={item.name}
            onChange={(e) => onChange({ ...item, name: e.target.value })}
            placeholder="Summarize"
          />
        </div>
        <Input
          label="Description"
          value={item.description ?? ''}
          onChange={(e) => onChange({ ...item, description: e.target.value })}
          placeholder="Short description"
        />
        <Input
          label="Slash command"
          value={item.slash_command}
          onChange={(e) => onChange({ ...item, slash_command: e.target.value })}
          placeholder="/summarize"
        />
        <p className="asset-form-help">Must start with / (e.g. /summarize). Auto-prepended if missing.</p>
        <label>
          <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>System prompt addendum</span>
          <textarea
            className="asset-form-textarea"
            value={item.system_prompt_addendum}
            onChange={(e) => onChange({ ...item, system_prompt_addendum: e.target.value })}
            placeholder="Additional instructions appended when this command is invoked..."
          />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            type="checkbox"
            checked={item.enabled}
            onChange={(e) => onChange({ ...item, enabled: e.target.checked })}
          />
          <span>Enabled</span>
        </label>
        {error && <p className="asset-form-error">{error}</p>}
      </div>
    </Modal>
  );
}
