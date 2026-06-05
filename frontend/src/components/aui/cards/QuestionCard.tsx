import { useState } from 'react';
import type { CardDescriptor, QuestionItem } from '../../../types';
import { CardShell } from '../CardShell';

export interface QuestionCardProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  /**
   * P7 (opencode 原生): 用户点击"提交"时触发, 携带所有 question 的答案
   * 二维数组, 顺序与 questions[] 一一对应。
   * 不走 turnService.resume — 父组件调 questionService.reply(requestId, answers, sessionId).
   */
  onSubmit?: (answers: string[][], actionId?: string) => void;
  /**
   * 忽略/拒绝 (前端"忽略"按钮 → questionService.reject).
   */
  onReject?: () => void;
  /**
   * 实际待回答 question 列表 (来自 opencode ``question.asked`` 事件).
   * 不传时尝试从 ``card.body.questions`` 读。
   */
  questions?: QuestionItem[];
  requestId?: string;
  sessionId?: string;
}

// QUESTION — 仿 opencode 原生 question UI:
//  - 1/N 折叠计数
//  - 每个 question: header (短标签) + question (主文) + Radio/Checkbox
//  - multiple=false 时单选 (Radio); multiple=true 时多选 (Checkbox 风格)
//  - custom=true 时显示"输入自己的答案"文本输入框
//  - 底部 "提交" / "忽略" 按钮
//  - 答案收集: 受控模式, 父组件传 picked/onPickedChange 同步状态
export function QuestionCard({
  card,
  suspended,
  submitted,
  onSubmit,
  onReject,
  questions: questionsProp,
  requestId,
  sessionId,
}: QuestionCardProps) {
  const questions = (questionsProp ??
    (Array.isArray(card.body?.questions) ? (card.body!.questions as QuestionItem[]) : [])) as QuestionItem[];
  const total = questions.length;

  // 选中的 label 列表, 顺序与 questions[] 对应
  const [picked, setPicked] = useState<string[][]>(() => questions.map(() => []));
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);

  if (total === 0) {
    return (
      <CardShell card={card} suspended={suspended} submitted={submitted}>
        <p className="aui-card-message">（无问题）</p>
      </CardShell>
    );
  }

  const isDone = suspended || submitted;

  const updatePicked = (idx: number, labels: string[]) => {
    setPicked((prev) => {
      const next = prev.slice();
      next[idx] = labels;
      return next;
    });
  };

  const handleConfirm = () => {
    if (busy || isDone) return;
    if (!picked.some((p) => p.length > 0)) return; // 至少一题有答案
    setBusy(true);
    onSubmit?.(picked, 'submit');
  };

  const handleReject = () => {
    if (busy || isDone) return;
    setBusy(true);
    onReject?.();
  };

  return (
    <CardShell
      card={card}
      suspended={suspended}
      submitted={submitted}
      footer={
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          {onReject && !isDone && (
            <button
              type="button"
              className="aui-action aui-action-ghost"
              onClick={handleReject}
              disabled={busy}
            >
              忽略
            </button>
          )}
          {onSubmit && !isDone && (
            <button
              type="button"
              className="aui-action aui-action-primary"
              onClick={handleConfirm}
              disabled={busy || !picked.some((p) => p.length > 0)}
            >
              提交
            </button>
          )}
          {isDone && (
            <span className="aui-card-badge aui-card-badge-done">
              {submitted ? '已提交' : '已忽略'}
            </span>
          )}
        </div>
      }
    >
      <div className="aui-question-meta" hidden>
        <code>{requestId}</code>
        <code>{sessionId}</code>
      </div>
      {questions.map((q, idx) => (
        <QuestionItemRow
          key={idx}
          index={idx}
          total={total}
          item={q}
          picked={picked[idx] ?? []}
          onChange={(labels) => updatePicked(idx, labels)}
          disabled={isDone}
          collapsed={collapsed.has(idx)}
          onToggle={() =>
            setCollapsed((prev) => {
              const next = new Set(prev);
              if (next.has(idx)) next.delete(idx);
              else next.add(idx);
              return next;
            })
          }
        />
      ))}
    </CardShell>
  );
}

interface QuestionItemRowProps {
  index: number;
  total: number;
  item: QuestionItem;
  picked: string[];
  onChange: (labels: string[]) => void;
  disabled: boolean;
  collapsed: boolean;
  onToggle: () => void;
}

function QuestionItemRow({
  index,
  total,
  item,
  picked,
  onChange,
  disabled,
  collapsed,
  onToggle,
}: QuestionItemRowProps) {
  const [customText, setCustomText] = useState<string>('');
  // opencode 的 multiple 默认是 true (除非显式 false) — 但单选场景居多
  // 用 options.length > 1 启发式: >1 时多选, 1 时单选
  const multiple = item.multiple === true || (item.multiple === undefined && (item.options?.length ?? 0) > 1);
  const allowCustom = item.custom !== false;
  const usingCustom = allowCustom && customText.trim().length > 0;

  const toggleOption = (label: string) => {
    if (disabled) return;
    if (multiple) {
      if (picked.includes(label)) {
        onChange(picked.filter((l) => l !== label));
      } else {
        onChange([...picked, label]);
      }
    } else {
      onChange([label]);
    }
    setCustomText('');
  };

  const setCustom = (text: string) => {
    setCustomText(text);
    if (text.trim().length > 0) {
      // 自定义答案用 __custom__ 标记, 让 opencode 服务端读 input
      onChange(['__custom__']);
    } else {
      onChange([]);
    }
  };

  return (
    <div className="aui-question-item">
      <div className="aui-question-item-header">
        <span className="aui-question-counter">
          {index + 1}/{total}
        </span>
        {item.header && (
          <span className="aui-question-tag">{item.header}</span>
        )}
        <button
          type="button"
          className="aui-question-toggle"
          onClick={onToggle}
          aria-label={collapsed ? '展开' : '折叠'}
        >
          {collapsed ? '+' : '−'}
        </button>
      </div>
      {!collapsed && (
        <>
          <p className="aui-question-prompt">{item.question}</p>
          <div className="aui-question-options">
            {(item.options ?? []).map((opt, oi) => {
              const isSelected = !usingCustom && picked.includes(opt.label);
              return (
                <button
                  type="button"
                  key={`${opt.label}-${oi}`}
                  className={`aui-question-option ${isSelected ? 'selected' : ''}`}
                  onClick={() => toggleOption(opt.label)}
                  disabled={disabled}
                >
                  <span
                    className={`aui-question-radio ${multiple ? 'is-multi' : ''} ${
                      isSelected ? 'is-checked' : ''
                    }`}
                    aria-hidden="true"
                  />
                  <span className="aui-question-option-main">
                    <span className="aui-question-option-label">{opt.label}</span>
                    {opt.description && (
                      <span className="aui-question-option-desc">
                        {opt.description}
                      </span>
                    )}
                  </span>
                </button>
              );
            })}
            {allowCustom && (
              <div
                className={`aui-question-custom ${usingCustom ? 'selected' : ''}`}
              >
                <span
                  className={`aui-question-radio ${usingCustom ? 'is-checked' : ''}`}
                  aria-hidden="true"
                />
                <div className="aui-question-custom-body">
                  <div className="aui-question-option-label">输入自己的答案</div>
                  <input
                    type="text"
                    className="aui-question-custom-input"
                    placeholder="输入你的答案..."
                    value={customText}
                    onChange={(e) => setCustom(e.target.value)}
                    disabled={disabled}
                  />
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
