import type { TodoItem, TodoPriority, TodoStatus } from '../../../types';
import { CardShell } from '../CardShell';
import type { CardDescriptor } from '../../../types';

export interface TodoListCardProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  /**
   * 实际任务清单 — 来自 opencode ``todo.updated`` 事件, 父组件渲染时把
   * ``todos`` 传过来。如果没传, 尝试从 ``card.body.todos`` 读。
   */
  todos?: TodoItem[];
  onSubmit?: (userInput: Record<string, unknown>, actionId?: string) => void;
}

// TODO_LIST — 任务清单 (opencode 原生 todowrite 工具写入)
// 按 status 分组: in_progress → pending → completed → cancelled
// 每项左侧 priority 图标 (high/medium/low), 右侧 status 标签
export function TodoListCard({
  card,
  suspended,
  submitted,
  todos: todosProp,
}: TodoListCardProps) {
  const todos = (todosProp ??
    (Array.isArray(card.body?.todos) ? (card.body!.todos as TodoItem[]) : [])) as TodoItem[];
  if (todos.length === 0) {
    return (
      <CardShell card={card} suspended={suspended} submitted={submitted}>
        <p className="aui-card-message">（暂无任务）</p>
      </CardShell>
    );
  }

  const groups: Record<string, TodoItem[]> = {
    in_progress: [],
    pending: [],
    completed: [],
    cancelled: [],
  };
  for (const t of todos) {
    const key = (t.status || 'pending') as TodoStatus;
    if (groups[key]) groups[key].push(t);
    else groups.pending.push(t);
  }
  const orderedKeys = ['in_progress', 'pending', 'completed', 'cancelled'] as const;

  return (
    <CardShell card={card} suspended={suspended} submitted={submitted}>
      <div className="aui-todo-list">
        {orderedKeys.map((key) => {
          const items = groups[key];
          if (!items || items.length === 0) return null;
          return (
            <div key={key} className={`aui-todo-group aui-todo-${key}`}>
              <div className="aui-todo-group-header">
                {labelForStatus(key)} <span className="aui-todo-count">{items.length}</span>
              </div>
              <ul className="aui-todo-items">
                {items.map((t, i) => (
                  <li key={`${t.content}-${i}`} className="aui-todo-item">
                    <span
                      className={`aui-todo-priority aui-todo-priority-${t.priority}`}
                      title={labelForPriority(t.priority)}
                    >
                      {iconForPriority(t.priority)}
                    </span>
                    <span className="aui-todo-content">{t.content}</span>
                    {t.status === 'in_progress' && (
                      <span className="aui-todo-badge">进行中</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </CardShell>
  );
}

function labelForStatus(s: string): string {
  switch (s) {
    case 'in_progress':
      return '进行中';
    case 'pending':
      return '待办';
    case 'completed':
      return '已完成';
    case 'cancelled':
      return '已取消';
    default:
      return s;
  }
}

function labelForPriority(p: TodoPriority): string {
  switch (p) {
    case 'high':
      return '高优先级';
    case 'medium':
      return '中优先级';
    case 'low':
      return '低优先级';
    default:
      return p;
  }
}

function iconForPriority(p: TodoPriority): string {
  switch (p) {
    case 'high':
      return '●';
    case 'medium':
      return '◐';
    case 'low':
      return '○';
    default:
      return '·';
  }
}
