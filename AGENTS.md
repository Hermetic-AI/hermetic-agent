# AGENTS.md — hermetic-agent

> Sanic 网关 + Scenario 编排层 + opencode / claude-agent 双 SDK 适配。Python 3.10+，前端 React + Vite + TS。

---

## 0. 必读 vs 本文件

**详细协作守则、5 层架构定义、import 约定、错误码、占位符**全部在：

- `.ai/AGENTS.md` — Coding Agent 守则（5 层 / 文件大小 / 命名 / 错误码 / 自检清单）
- `.ai/CLAUDE.md` — 项目总览、命令速查、SDK 对比、StreamEvent 12 种
- `docs/architecture-and-flow.md` — 5 层 + 对话流程 4 种情形 + 12 错误码
- `docs/api.md` + `docs/openapi.json` — REST 契约

**本文件只列高信号 / 易踩坑事项**，避免重复。

---

## 1. 仓库结构（先认路）

| 路径 | 角色 |
|---|---|
| `src/hermetic_agent/` | Hub 主代码（5 层架构，CI 强校验） |
| `frontend/` | **活跃前端**（React + Vite + TS，`frontend/src/`） |
| `frontend/related_project/agent_chat_web/` | **旧 Vue 3 + Element Plus 前端** — 参考用，**不要** `cd` 进去 `pnpm dev` |
| `work/` | 运行时：scenarios YAML / shared skills / mcp config / tenant 目录（容器内 `/app/work`） |
| `bake/` | 历史归档（老 scenario / skill 草稿），**不要**与 `work/` 混用 |
| `docker/` | 3 份 Dockerfile（Hub / opencode-sandbox / frontend）+ nginx.conf + entrypoint + sandbox admin/health server |
| `docs/` | 设计文档、API 契约、部署指南、变更报告 |
| `relate_project/opencode/` 与 `relate_project/opencode-sdk-python/` | **只读参考**：opencode 上游 + Python SDK 源码 |
| `scripts/ci_check.py` | 自研 5 层 + 文件大小 lint |
| `scripts/check_unified_chat_entry.py` | 统一 chat 入口约束（见 §3） |
| `scripts/verify_opencode_config.py` | opencode 沙箱诊断（source / container cfg / chat smoke 3 项） |

---

## 2. 命令速查

```bash
# 安装（uv 优先 — .venv + uv.lock 已就位）
uv venv && uv pip install -e ".[dev]"

# 启动 Hub（无 opencode 沙箱时仅能 API 探活，chat 走不通）
hermetic-agent                              # 等价 python -m hermetic_agent.main
AGENT_SCHEDULER_STORAGE_BACKEND=memory hermetic-agent   # 强制内存存储

# 测试（pytest-asyncio auto mode — 无需 @pytest.mark.asyncio）
pytest -v                                    # 全量
pytest tests/test_<file>.py -v               # 单文件
pytest tests/ -k "test_xxx" -v               # 单用例 / 子串匹配
pytest tests/test_e2e_* -v --run-e2e         # e2e 默认 skip，需显式 flag

# Lint / 类型
ruff check src/                              # line-length=100, ignore=E501
mypy src/                                    # strict=True

# 质量门禁（提交前必跑 — 失败 = 拒）
python scripts/ci_check.py
python scripts/check_unified_chat_entry.py
```

---

## 3. 绝对约束（CI 拦截，不要绕过）

1. **统一 chat 入口**。只有 2 个端点，都集中在 `src/hermetic_agent/api/controllers/chat_controller.py`：
   - `POST /agent/chat`（同步 JSON）
   - `POST /agent/chat/stream`（SSE）

   ❌ 禁止：`/agent/scenarios/{name}/chat[/stream]`、其他 controller / 前端 service 另起 chat handler。
   Scenario 路由在 `ScenarioMiddleware.route()` 的 6 优先级里完成（URL path hint → `X-Scenario` header → body 关键词 → `body.scenario` → LLM 意图分类 → `_generic` 兜底）。

2. **5 层依赖严格向下**（`scripts/ci_check.py` 扫 `import-from`）：

   ```
   L1 api/            → L2, L3
   L2 scenarios/      → L3
   L3 skill_runtime/ + auip/ + core/suspendable_scheduler.py + core/turn_store.py → L4, L5
   L4 providers/      → L5
   L5 policy/ + store/ + audit/ → (无)
   ```

   反向引用、跨层跳引一律 fail。

3. **文件大小硬上限**（`scripts/ci_check.py` 验）：
   - L1 / L4 / L5 ≤ 200 行
   - L2 / L3 ≤ 250 行
   - 函数 ≤ 40 行
   - 已知豁免见 `KNOWN_VIOLATIONS` 常量；**新增代码不允许再列豁免**。

4. **零修改既有签名**：`core/scheduler.py` / `providers/*.py` / `skills/registry.py` / `mcp/registry.py` 等已有类的签名不改；扩展请新建 wrapper。

5. **错误码 12 个**（`docs/architecture-and-flow.md` §7）：所有用户可见错误必须用 `code` + `detail`（哪个文件/字段/规则/怎么改）。**禁止**只返回 `"error"`。

---

## 4. 配置（`src/hermetic_agent/config/settings.py`）

- 唯一配置中心：`pydantic-settings` + 前缀 `AGENT_SCHEDULER_`，CWD 下的 `.env` 自动加载。
- 复杂字段（`list[dict]`）支持 inline JSON **或** JSON 文件路径（`env_sources.PathAwareEnvSource`）。
- **不要**在模块顶层或函数默认值里写硬编码常量；统一 `from hermetic_agent.config.settings import get_settings`。
- `pyproject.toml` 与 `requirements.txt` **必须保持同步**（镜像构建依赖 docker `COPY requirements.txt`，改了 deps 两边一起改，否则 BuildKit 缓存命中不到 → 见 `docs/BUILD.md`）。

---

## 5. 容器与部署

3 个 service 单 `docker-compose.yml`：

| Service | 端口 (host→container) | 角色 | 默认启用 |
|---|---|---|---|
| `hermetic-agent` | `28000→8000` | Hub 主服务 | ✅ |
| `opencode-1` | `24096`, `27778` (admin 调试) | opencode sandbox 节点 | ✅ |
| `hermetic_agent-frontend` | `23000→13000` | nginx 反代 + 静态 | ❌ (`--profile frontend`) |

2 种模式靠 **`PULL_POLICY`** 切换：

| 值 | 行为 | 用法 |
|---|---|---|
| `missing`（默认） | 本地有就用，没才拉 | `docker compose up -d --build`（local / dev） |
| `always` | 强制从 registry 拉 | `PULL_POLICY=always docker compose up -d`（生产） |

加 frontend：`docker compose --profile frontend up -d --build`。

镜像 tag 走 env：`HERMETIC_AGENT_HUB_IMAGE` / `OPENCODE_SANDBOX_IMAGE` / `HERMETIC_AGENT_FRONTEND_IMAGE`。

**`WORKSPACE_PATH` 关键约束**：host 与容器**必须同路径**（agent 透明），否则 sandbox 在容器内写文件后 host 看不到。

**改 model / key / env 不重建镜像**：走 sandbox admin API（`POST :27778/admin/policy`、`/admin/env`、`/admin/reload`）或 Hub 代理（`POST :28000/agent/admin/opencode/opencode-1/...`）。

**改 scenario / skill / mcp YAML**：ro bind 进容器，`docker compose restart hermetic-agent` 即可，**不要 rebuild**。

要 N 个 opencode 节点：复制 `opencode-1` 块，改 `hostname: opencode-N`。

详细：`docs/deploy.md` + `docs/BUILD.md`。

---

## 6. 测试

- `pytest-asyncio`，`asyncio_mode = "auto"` — 不用 `@pytest.mark.asyncio`。
- **不要改 `tests/conftest.py`**（read-only）。新 fixture 放 `tests/test_<feature>_conftest.py`。
- 命名约定：`test_<module>_{init,happy_path,error}_*`。
- e2e 用例（`test_e2e_*`）默认 skip，需凭据 + 真实沙箱才会跑。
- `work/` 改动不用 rebuild；`src/hermetic_agent/**/*.py` 改动才需要 `docker compose build hermetic-agent`（BuildKit cache，增量 ~9s — 见 `docs/BUILD.md`）。

---

## 7. 资源 & 占位符

- Scenario 资源根 = `work/`（容器内 `/app/work`），所有相对路径从这算。
- YAML 占位符在 `ScenarioLoader.load` 时解析：`${PROJECT_DIR}` / `${SCENARIO_DIR}` / `${WORK_ROOT}` / `${WORK_SHARED}` / `${TENANT_ID}` / `${USER_ID}` / `${AGENT_NAME}` / `${MODEL}`。
- Skill 开发：`docs/skills-development-guide.md`。

---

## 8. 提交前自检

```bash
cd "C:\WorkSpace\Coding\hermetic_agent"
python scripts/ci_check.py                 # 必须 0 NEW 违规
python scripts/check_unified_chat_entry.py # 必须 PASS
ruff check src/hermetic_agent/<your_module>/
mypy src/hermetic_agent/<your_module>/
pytest tests/test_<your_module>_*.py -v
```

任何失败**自己修**，不要留给用户。

---

## 9. 调试指北

- Hub 报 `ProviderModelNotFoundError` → `python scripts/verify_opencode_config.py`（source / container cfg / chat smoke 3 项；失败会打印精确修复命令）。
- opencode 升级后老 session 报 `ProviderModelNotFoundError` → 让 client 发新 session id（前端清 session_storage），或 `docker compose build opencode-1 --no-cache`。
- frontend 容器循环重启（`chown ... client_temp` / `setgid(101) failed`）→ `cap_drop` 不能用 `ALL`，要保留 `CAP_CHOWN` / `CAP_SETUID` / `CAP_SETGID` / `CAP_DAC_OVERRIDE`。完整解释 `docs/deploy.md` Troubleshooting。
- Port 23000 被占用（`vite` dev server）→ `ps aux | grep vite` 找进程 kill，或改 compose host 端口为 `23100:13000`。
- 改了 `src/hermetic_agent/` 内文件但容器内未生效 → `docker compose build hermetic-agent`（仅 `restart` 不会拉新代码）。
- 改了 `pyproject.toml` deps 但 install 报缺包 → 同步改 `requirements.txt`（镜像构建 cache 命中条件）。
