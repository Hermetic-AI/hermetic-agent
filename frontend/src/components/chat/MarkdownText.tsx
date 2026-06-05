// MarkdownText — chat 场景下的 markdown 渲染.
//
// 设计要点:
//   1. 用 react-markdown + remark-gfm 处理标准 + GFM 语法.
//   2. react-markdown 默认禁掉原始 HTML (XSS 安全).
//   3. 流式兼容: 未闭合的 **bo / ```js / [text]( 不会尝试渲染,会当文本展示;
//      闭合瞬间 (例 **bold**) 立刻升级成 <strong>. 这跟 ChatGPT/Claude 行为一致.
//   4. 不重置列表/段落样式 (依赖 .markdown-body 类), 跟 chat-bubble 风格统一.
//
// 真实接入: LLM 输出走 Bash 调 MCP 的场景里, 工具 result 已经是 JSON, 不会再
// 套 markdown; 这里只处理 chat 主体的纯文本消息.

import { memo, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './MarkdownText.css';

interface MarkdownTextProps {
  source: string;
  /** Streaming 中显示光标 (替代 markdown 解析后的内容尾部). */
  showCursor?: boolean;
}

function MarkdownTextInner({ source, showCursor = false }: MarkdownTextProps) {
  // react-markdown 的 props 在 source 变化时会触发整树重解析, 没问题.
  // 用 useMemo 防止父组件重渲时无谓重复解析 (虽然 react-markdown 内部也 memo).
  const normalized = useMemo(() => normalizeMarkdown(source), [source]);

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        // 链接默认在新标签页打开 (差旅场景下, AI 引用航司/酒店政策时常用)
        components={{
          a: ({ node: _node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
        }}
      >
        {normalized}
      </ReactMarkdown>
      {showCursor && <span className="markdown-cursor">▍</span>}
    </div>
  );
}

/**
 * 简单的流式友好预处理:
 *   - 把尾部未闭合的代码围栏 ```` 去掉, 避免半个 fence 永远等不到闭合
 *     把整个文本冻在"代码块未闭合"状态.
 *   - 段尾多于 2 个连续空行压缩成 1 个 (LLM 偶尔会输出 "\n\n\n\n" 让段落变怪).
 * 这一步不影响闭合良好的 markdown; 只救流式时最后那个未完成的 token.
 */
function normalizeMarkdown(src: string): string {
  if (!src) return src;
  let s = src.replace(/\n{3,}/g, '\n\n');
  // 如果末尾有奇数个 ```, 把最后一个去掉 (防止 fence 永远不闭合)
  const fences = (s.match(/```/g) || []).length;
  if (fences % 2 === 1) {
    const lastIdx = s.lastIndexOf('```');
    s = s.slice(0, lastIdx);
  }
  return s;
}

export const MarkdownText = memo(MarkdownTextInner);
