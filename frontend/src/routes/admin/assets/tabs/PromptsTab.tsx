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
import { promptsApi } from '../../../services/prompts';
import type { PromptAsset } from '../../../types/assets';
import '../index.css';
import './PromptsTab.css';

const NEW_PROMPT: Omit<PromptAsset, 'id' | 'created_at' | 'updated_at' | 'owner_user_id' | 'visibility' | 'version'> = {
  code: '',
  name: '',
  description: '',
  status: 'draft',
  content: '',
};

export function PromptsTab() {
  const [items, setItems] = useState<PromptAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<typeof NEW_PROMPT | null>(null);
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<PromptAsset | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { loadList(); }, []);

  async function loadList() {
    setLoading(true);
    try {
      const r = await promptsApi.list();
      setItems(r.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  function openNew() {
    setEditing({ ...NEW_PROMPT });
    setEditingCode(null);
    setError(null);
  }

  function openEdit(item: PromptAsset) {
    setEditing({
      code: item.code,
      name: item.name,
      description: item.description ?? '',
      status: item.status,
      content: item.content,
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
    setSaving(true);
    setError(null);
    try {
      if (editingCode) {
        await promptsApi.update(editingCode, editing);
      } else {
        await promptsApi.create(editing);
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
      await promptsApi.delete(deleting.code);
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
        <h2>Prompts ({items.length})</h2>
        <Button variant="primary" onClick={openNew}>+ New Prompt</Button>
      </div>
      {error && <p className="asset-form-error">{error}</p>}
      {loading ? <Skeleton variant="rectangular" height={120} /> :
       items.length === 0 ? (
         <Empty
           title="No prompts yet"
           description="Create your first prompt to get started."
           action={{ label: 'Create first', onClick: openNew }}
         />
       ) : (
         <div className="assets-tab-grid">
           {items.map((item) => (
             <Card key={item.code}>
               <CardHeader>
                 <strong>{item.name}</strong>
                 <span className={`asset-status-badge asset-status-${item.status}`}>{item.status}</span>
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
                     <span className="asset-card-meta-label">Content:</span>
                     <span>{item.content.length} chars</span>
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
        <PromptEditDialog
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
          title="Delete prompt"
          message={`Delete prompt ${deleting.code}? This cannot be undone.`}
          confirmText="Delete"
          variant="danger"
        />
      )}
    </div>
  );
}

interface PromptEditDialogProps {
  item: typeof NEW_PROMPT;
  isNew: boolean;
  saving: boolean;
  error: string | null;
  onChange: (next: typeof NEW_PROMPT) => void;
  onSave: () => void;
  onClose: () => void;
}

function PromptEditDialog({ item, isNew, saving, error, onChange, onSave, onClose }: PromptEditDialogProps) {
  return (
    <Modal
      open
      onClose={onClose}
      title={isNew ? 'New Prompt' : `Edit Prompt: ${item.code}`}
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
            placeholder="my-prompt"
          />
          <Input
            label="Name"
            value={item.name}
            onChange={(e) => onChange({ ...item, name: e.target.value })}
            placeholder="My Prompt"
          />
        </div>
        <Input
          label="Description"
          value={item.description ?? ''}
          onChange={(e) => onChange({ ...item, description: e.target.value })}
          placeholder="Short description"
        />
        <label>
          <span style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 4 }}>Content</span>
          <textarea
            className="asset-form-textarea"
            value={item.content}
            onChange={(e) => onChange({ ...item, content: e.target.value })}
            placeholder="Prompt template..."
          />
        </label>
        <p className="asset-form-help">
          The content is sent to the model as the system prompt. Use {`{{variable}}`} placeholders.
        </p>
        {error && <p className="asset-form-error">{error}</p>}
      </div>
    </Modal>
  );
}
