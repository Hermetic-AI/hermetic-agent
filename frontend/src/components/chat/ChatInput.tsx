import { useState, useRef, useCallback, useEffect, type FormEvent, type KeyboardEvent, type ChangeEvent } from 'react';
import { SendIcon } from './Icons';
import type { PromptAsset, CommandAsset, SkillAsset, McpConfigAsset } from '../../types/assets';
import type { AssetInvokeRequest } from '../../lib/events';
import './ChatInput.css';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
  /**
   * Initial text to prefill the input with.  Set once when the prop
   * transitions from `undefined` to a string (typical pattern: parent
   * remounts the input on a "use asset" event, so this fires on mount).
   */
  initialValue?: string;
  /** Full list of prompt assets (parent fetches via usePrompts / promptsApi). */
  prompts: PromptAsset[];
  /** Full list of command assets. */
  commands: CommandAsset[];
  /** Full list of skill assets. */
  skills: SkillAsset[];
  /** Full list of mcp config assets. */
  mcps: McpConfigAsset[];
  /**
   * Parent hook for emitting `ASSET_INVOKE_EVENT` and adding the code to
   * `activePrompts` / `activeSkills` / `activeMcps` / `agentCode`.
   * ChatInput is pure UI — it never touches the store directly.
   */
  onAssetInvoked: (req: AssetInvokeRequest) => void;
  /**
   * Parent hook for emitting `COMMAND_EXECUTED_EVENT` and pushing to
   * `executedCommands`.  The parent's `useChatStream.send()` integration
   * (appending the command's `system_prompt_addendum` as a synthetic
   * user message) is the next step.
   */
  onCommandExecuted: (code: string, slash: string, summary: string) => void;
}

type TriggerKind = 'at' | 'slash';

interface TriggerState {
  kind: TriggerKind;
  query: string;
  /** Textarea selectionStart at the moment the trigger character was typed. */
  start: number;
}

type AssetEntry =
  | { section: 'prompts'; code: string; name: string; description: string | null; type: 'prompt' }
  | { section: 'commands'; code: string; name: string; description: string | null; slash: string; type: 'command' }
  | { section: 'skills'; code: string; name: string; description: string | null; type: 'skill' }
  | { section: 'mcps'; code: string; name: string; description: string | null; type: 'mcp' };

const MAX_POPOVER_ITEMS = 8;
const MAX_POPOVER_SECTIONS = 4;

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = 'Message AI...',
  initialValue = '',
  prompts,
  commands,
  skills,
  mcps,
  onAssetInvoked,
  onCommandExecuted,
}: ChatInputProps) {
  const [value, setValue] = useState(initialValue);
  const [trigger, setTrigger] = useState<TriggerState | null>(null);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const hasAppliedInitial = useRef(initialValue !== '');

  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, []);

  // If the parent flips `initialValue` to a non-empty value after mount
  // (e.g. async asset resolution finishes), pick it up.  Guarded with a ref
  // so a value that happens to equal what the user already typed doesn't
  // clobber their cursor.
  useEffect(() => {
    if (!hasAppliedInitial.current && initialValue) {
      setValue(initialValue);
      hasAppliedInitial.current = true;
      adjustHeight();
    }
  }, [initialValue, adjustHeight]);

  // Build the visible popover list for the current trigger + query.
  const popoverEntries: AssetEntry[] = trigger ? buildEntries(trigger, prompts, commands, skills, mcps) : [];
  const clampedSelected = popoverEntries.length === 0 ? 0 : Math.min(selectedIdx, popoverEntries.length - 1);

  // Reset selection whenever the trigger or query changes.
  useEffect(() => {
    setSelectedIdx(0);
  }, [trigger?.kind, trigger?.query]);

  const closePopover = useCallback(() => {
    setTrigger(null);
    setSelectedIdx(0);
  }, []);

  /**
   * Detect an open `@token` or `/token` at the textarea cursor.
   * Returns the trigger state, or null if the user is not inside a token.
   * A token is "open" when:
   *   - it starts with `@` or `/`
   *   - the rest of the token contains no whitespace
   *   - the character before the trigger is not a word char (so
   *     `foo@bar` doesn't open a popover).
   */
  const detectTrigger = useCallback((text: string, cursor: number): TriggerState | null => {
    const before = text.slice(0, cursor);
    for (const kind of ['at', 'slash'] as const) {
      const ch = kind === 'at' ? '@' : '/';
      const idx = before.lastIndexOf(ch);
      if (idx < 0) continue;
      // Must be at the start of the buffer OR preceded by whitespace / punctuation.
      if (idx > 0) {
        const prev = before[idx - 1];
        if (/[A-Za-z0-9_]/.test(prev)) continue;
      }
      // No whitespace inside the token.
      const tail = before.slice(idx + 1);
      if (/\s/.test(tail)) continue;
      return { kind, query: tail.toLowerCase(), start: idx };
    }
    return null;
  }, []);

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const next = e.target.value;
    setValue(next);
    adjustHeight();

    // "Robust" trigger behaviour: if the user types past a popover and
    // adds whitespace (or any non-`@`/`/` character that ends the token),
    // we auto-commit whatever the popover's current entry was.  This
    // matches Slack/Notion: typing `@alice ` after the popover
    // confirms the selection even if the user never pressed Enter.
    //
    // Specifically: if we had a trigger open, and the new value still
    // contains the trigger character with the same query, the user is
    // just typing more characters (no close).  If the new value lost
    // the trigger character (e.g. backspace) or grew whitespace after
    // the query, the trigger just closed — commit the highlighted
    // entry, but ONLY when the previous query was non-empty (otherwise
    // the user never selected anything).
    if (trigger && trigger.query) {
      const cursor = e.target.selectionStart ?? next.length;
      const newTrigger = detectTrigger(next, cursor);
      if (newTrigger === null) {
        // Trigger closed on its own (whitespace added, or @ backspaced).
        // The "completed by typing" case: prev value has `<ch><query>`
        // and next value has `<ch><query><space>` or similar.  Detect by
        // checking that next still contains the original trigger token
        // somewhere followed by whitespace.
        const ch = trigger.kind === 'at' ? '@' : '/';
        const q = trigger.query;
        const completedTokenRe = new RegExp(
          `(^|\\s)${escapeRegExp(ch + q)}\\s`,
        );
        const wasCompletedByTyping = completedTokenRe.test(next);
        if (wasCompletedByTyping) {
          const entry = popoverEntries[clampedSelected];
          if (entry) {
            // Strip the token.  We can't call handleSelectEntry here
            // because it would re-strip the same token (we're already
            // doing the strip).  Inline the bare minimum.
            const tokenRe = new RegExp(
              `(^|\\s)${escapeRegExp(ch + q)}\\s?`,
            );
            const stripped = next.replace(tokenRe, (_m, lead) => lead);
            setValue(stripped);
            adjustHeight();
            if (entry.type === 'command') {
              onCommandExecuted(entry.code, entry.slash, entry.description ?? entry.name);
            }
            onAssetInvoked({
              type: entry.type,
              code: entry.code,
              source: 'chat-input',
              preview: entry.type === 'command' ? (entry.description ?? entry.name) : undefined,
            });
            setTrigger(null);
            return;
          }
        }
        // Otherwise the user backspaced — just close the popover
        // without binding anything.
        setTrigger(null);
        return;
      }
      setTrigger(newTrigger);
      return;
    }

    setTrigger(detectTrigger(next, e.target.selectionStart ?? next.length));
  };

  const handleSelectEntry = useCallback(
    (entry: AssetEntry) => {
      if (!trigger) return;
      // All trigger types (including @prompt / @skill / @mcp) "consume"
      // the trigger token — the asset is bound to the active set via
      // onAssetInvoked, but we do NOT leave `@code` text in the input.
      // This matches Slack / Notion / Cursor UX: @ is a trigger, not a
      // label.  The cursor lands back where it was before the `@` so the
      // user can immediately type their actual question.
      const ta = textareaRef.current;
      if (ta) {
        const end = ta.selectionStart ?? trigger.start + 1 + trigger.query.length;
        const before = value.slice(0, trigger.start);
        const after = value.slice(end);
        const next = (before + after).replace(/^\s+/, '');
        setValue(next);
        adjustHeight();
        const cursor = Math.min(before.length, next.length);
        requestAnimationFrame(() => {
          ta.focus();
          ta.setSelectionRange(cursor, cursor);
        });
      }
      if (entry.type === 'command') {
        const summary = entry.description ?? entry.name;
        onCommandExecuted(entry.code, entry.slash, summary);
      }
      onAssetInvoked({
        type: entry.type,
        code: entry.code,
        source: 'chat-input',
        preview: entry.type === 'command' ? (entry.description ?? entry.name) : undefined,
      });
      setTrigger(null);
      setSelectedIdx(0);
    },
    [trigger, value, adjustHeight, onAssetInvoked, onCommandExecuted],
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (trigger && popoverEntries.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIdx((i) => (i + 1) % popoverEntries.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIdx((i) => (i - 1 + popoverEntries.length) % popoverEntries.length);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        const entry = popoverEntries[clampedSelected];
        if (entry) handleSelectEntry(entry);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        closePopover();
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim() && !disabled) {
      onSend(value.trim());
      setValue('');
      closePopover();
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const canSend = value.trim().length > 0 && !disabled;
  const showPopover = !!trigger && popoverEntries.length > 0;

  return (
    <form className="chat-input-form" onSubmit={handleSubmit}>
      <div className="chat-input-container">
        <textarea
          ref={textareaRef}
          className="chat-input"
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
        />
        <button
          type="submit"
          className={`chat-send-btn ${canSend ? 'is-active' : ''}`}
          disabled={!canSend}
          aria-label="Send"
        >
          <SendIcon />
        </button>
        {showPopover && trigger && (
          <TriggerPopover
            kind={trigger.kind}
            entries={popoverEntries}
            selectedIdx={clampedSelected}
            query={trigger.query}
            onSelect={handleSelectEntry}
            onHover={setSelectedIdx}
          />
        )}
      </div>
      <div className="chat-input-hint">
        Press Enter to send · Shift+Enter for newline · @ to attach asset · / to run command
      </div>
    </form>
  );
}

interface TriggerPopoverProps {
  kind: TriggerKind;
  entries: AssetEntry[];
  selectedIdx: number;
  query: string;
  onSelect: (entry: AssetEntry) => void;
  onHover: (idx: number) => void;
}

function TriggerPopover({ kind, entries, selectedIdx, query, onSelect, onHover }: TriggerPopoverProps) {
  // Flatten with global indices so arrow-key selection maps across sections.
  let running = 0;
  const sections: Array<{ title: string; items: AssetEntry[] }> = [];
  if (kind === 'at') {
    const prompts = entries.filter((e) => e.section === 'prompts');
    const commands = entries.filter((e) => e.section === 'commands');
    const skills = entries.filter((e) => e.section === 'skills');
    const mcps = entries.filter((e) => e.section === 'mcps');
    if (prompts.length) sections.push({ title: 'Prompts', items: prompts });
    if (commands.length) sections.push({ title: 'Commands', items: commands });
    if (skills.length) sections.push({ title: 'Skills', items: skills });
    if (mcps.length) sections.push({ title: 'MCPs', items: mcps });
  } else {
    sections.push({ title: 'Commands', items: entries });
  }
  const limited = sections.slice(0, MAX_POPOVER_SECTIONS).map((s) => ({
    ...s,
    items: s.items.slice(0, MAX_POPOVER_ITEMS),
  }));

  return (
    <div className="chat-shell-popover" role="listbox" aria-label={kind === 'at' ? 'Asset picker' : 'Command picker'}>
      <div className="chat-shell-popover-arrow" aria-hidden="true" />
      {limited.length === 0 ? (
        <div className="chat-shell-popover-empty">No matches for "{query}"</div>
      ) : (
        limited.map((section) => (
          <div key={section.title} className="chat-shell-popover-section">
            <div className="chat-shell-popover-section-title">{section.title}</div>
            {section.items.map((entry) => {
              const globalIdx = running++;
              const isSelected = globalIdx === selectedIdx;
              const label = entry.type === 'command' ? entry.slash : `@${entry.code}`;
              return (
                <button
                  type="button"
                  key={`${entry.section}:${entry.code}`}
                  className={`chat-shell-popover-item ${isSelected ? 'is-selected' : ''}`}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => onHover(globalIdx)}
                  onClick={() => onSelect(entry)}
                  role="option"
                  aria-selected={isSelected}
                >
                  <span className="chat-shell-popover-item-label">{label}</span>
                  <span className="chat-shell-popover-item-name">{entry.name}</span>
                </button>
              );
            })}
          </div>
        ))
      )}
    </div>
  );
}

function buildEntries(
  trigger: TriggerState,
  prompts: PromptAsset[],
  commands: CommandAsset[],
  skills: SkillAsset[],
  mcps: McpConfigAsset[],
): AssetEntry[] {
  const q = trigger.query;
  const matchCode = (code: string, name: string, desc?: string | null) => {
    if (!q) return true;
    return (
      code.toLowerCase().includes(q) ||
      name.toLowerCase().includes(q) ||
      (desc ? desc.toLowerCase().includes(q) : false)
    );
  };
  if (trigger.kind === 'slash') {
    return commands
      .filter((c) => c.status === 'enabled' && c.enabled && matchCode(c.code, c.name, c.description))
      .map<AssetEntry>((c) => ({
        section: 'commands',
        code: c.code,
        name: c.name,
        description: c.description ?? null,
        slash: c.slash_command,
        type: 'command',
      }));
  }
  const out: AssetEntry[] = [];
  for (const p of prompts) {
    if (p.status !== 'enabled') continue;
    if (!matchCode(p.code, p.name, p.description)) continue;
    out.push({ section: 'prompts', code: p.code, name: p.name, description: p.description ?? null, type: 'prompt' });
  }
  for (const c of commands) {
    if (c.status !== 'enabled' || !c.enabled) continue;
    if (!matchCode(c.code, c.name, c.description)) continue;
    out.push({ section: 'commands', code: c.code, name: c.name, description: c.description ?? null, slash: c.slash_command, type: 'command' });
  }
  for (const s of skills) {
    if (s.status !== 'enabled') continue;
    if (!matchCode(s.code, s.name, s.description)) continue;
    out.push({ section: 'skills', code: s.code, name: s.name, description: s.description ?? null, type: 'skill' });
  }
  for (const m of mcps) {
    if (m.status !== 'enabled' || m.disabled) continue;
    if (!matchCode(m.code, m.name)) continue;
    out.push({ section: 'mcps', code: m.code, name: m.name, description: null, type: 'mcp' });
  }
  return out;
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
