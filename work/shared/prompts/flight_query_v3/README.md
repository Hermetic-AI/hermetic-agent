# flight_query_v3 — 共享 prompt 资源

> `flight_query_v3.scenario.yaml` 引用本目录(`resource_dirs.prompts: ${WORK_SHARED}/prompts/flight_query_v3`)。
> 当前 scenario 自身的 system_prompt 已经覆盖主流程(见 `execution.system_prompt`),
> 本目录用于放**跨 scenario 共享的 prompt 片段**(如身份文案、礼貌话术、合规提示等)。

## 当前文件

| 文件 | 用途 |
|---|---|
| (本 README) | 目录说明 |

## 约定

- 本目录放共享 prompt 片段,以 `.md` / `.txt` 形式,scenario 用 `${SCENARIO_DIR}` 或 `${WORK_SHARED}` 占位符引用
- 单一 scenario 私有 prompt 放 `${SCENARIO_DIR}/prompts/`(scenario 子目录下的 prompts)
- **不放**业务协议、endpoint、header、token — 那些是 MCP server 的事,跟 prompt 无关
