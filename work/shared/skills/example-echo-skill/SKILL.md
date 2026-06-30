---
name: example-echo-skill
version: 1.0.0
description: |
  示例 SKILL — 展示 hermetic-agent 的 SKILL 编写规范.
  不绑定任何具体业务, 仅演示 CardRenderer / MessageRewriter / env
  注入 / mcp_tools 声明的标准用法.

  真实业务 SKILL 应当:
  1. 在此 SKILL.md 改写 system_prompt 段为业务领域知识
  2. 在 skill.yaml 声明自己的 mcp_tools + required_envs
  3. 在 card_renderers/ 实现具体的 CardRenderer 子类
  4. 在 message_rewriters/ 实现具体的 MessageRewriter 子类
  5. 在 __init__.py 的 register_*() 入口注册到基座 Registry

  本 SKILL 仅做 echo 演示: LLM 调 echo 工具时, Hub 自动拼一张
  ECHO_RESULT card 给前端.
triggers:
  - "echo"
  - "回声"
input_schema:
  type: object
  required: [text]
  properties:
    text:
      type: string
      description: 用户希望 echo 的文本
output_schema:
  type: object
  required: [echoed, length]
  properties:
    echoed: { type: string }
    length: { type: integer }
---

# Example Echo Skill

> 业务 SKILL 模板 — 第三方开发者 fork 此目录, 改写为自己的业务.

## 1. SKILL 状态机

| State ID | Name           | Description                          |
|----------|----------------|--------------------------------------|
| S01      | AwaitEcho      | 等用户输入要 echo 的文本              |
| S02      | ShowResult     | 已经发出 ECHO_RESULT card, 等用户确认 |

## 2. 工具白名单

- `echo` (合成工具, Hub 注册)
- `ask_user` (框架级, Hub 注册)

## 3. Operating Rules

1. 收到用户消息时, 提取待 echo 的文本
2. 调 `echo` 合成工具 (Hub 会自动拼 ECHO_RESULT card)
3. 看到 ECHO_RESULT card 后, 询问用户是否继续

## 4. 完成定义

- 用户在 ECHO_RESULT card 上点击 "确认", 状态切到 F01
- 用户在 ECHO_RESULT card 上点击 "取消", 状态切到 S01
