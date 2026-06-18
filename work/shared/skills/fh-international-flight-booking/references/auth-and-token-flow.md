# Auth & Token Flow

> 加载时机：鉴权异常时加载本文件。

## Token 注入链路

```
前端登录 → 获得 token
  ↓
Hub chat_controller 拦截 → 提取 token
  ↓
_push_flight_token_to_opencode → POST sandbox:7778/admin/env  {"FLIGHT_API_KEY": "<token>"}
                              → POST sandbox:7778/admin/reload
  ↓
Agent 运行时 → os.environ["FLIGHT_API_KEY"] → http_client.py 自动注入 header
  ↓
每次 API 调用 → http_client.py api_post() → {"token": "<FLIGHT_API_KEY>"}
```

**注意**：国际机票与国内机票共用同一个 `FLIGHT_API_KEY` 环境变量。
Hub 的 `_push_flight_token_to_opencode` 函数在会话开始时将 token 写入容器的
`env.runtime` 文件，opencode 重启后从该文件 source。`http_client.py` 读取
`FLIGHT_API_KEY` 并注入到请求头的 `token` 字段。

## 环境变量

| 变量名 | 用途 | 默认值 |
|---|---|---|
| `FLIGHT_API_KEY` | 鉴权 token，注入到每个请求 header 的 `token` 字段 | 无（必须） |
| `FH_TRAVEL_BASE_URL` | fh-travel 后端地址 | `https://traveldev.feiheair.com` |

## Token 缺失处理

若 `FLIGHT_API_KEY` 为空或不存在：

1. **禁止**继续调用任何 API
2. **禁止**向用户索要 token（token 由系统管理，非用户输入）
3. 立即发 `CANNOT_ORDER` 卡片：
   ```json
   {
     "card_type": "CANNOT_ORDER",
     "title": "无法继续",
     "body": {
       "reason": "登录状态已失效，请重新登录后重试",
       "fallback": "刷新页面重新登录"
     }
   }
   ```

## Token 过期处理

API 返回 HTTP 401/403 或业务错误码指示 token 无效时：

1. **禁止**重试同一请求
2. **禁止**缓存旧 token 尝试绕过
3. 发 `CANNOT_ORDER` 卡片，reason 为"登录已过期，请重新登录"

## http_client.py 调用方式

Agent 通过 Bash 工具调用：

```bash
python3 skills/fh-international-flight-booking/scripts/http_client.py /air/international/intShopping body.json
# 或直接传 JSON 字符串：
python3 skills/fh-international-flight-booking/scripts/http_client.py /air/international/intShopping '{"tripList":[{"fromCity":"PEK","toCity":"NRT","flyDate":"2026-07-01","isCity":true}]}'
```

Token 自动从 `os.environ["FLIGHT_API_KEY"]` 读取并注入 `{"token": "..."}` header。

**注意**：沙箱内 Python 路径为 `python3`，不要用 `python`。

## 安全规则

- **不要**在回复中显示 token 值
- **不要**将 token 写入文件或日志
- **不要**让用户手动输入 token
- **不要**在 Markdown 表格或 PLAIN_TEXT 中包含 token
