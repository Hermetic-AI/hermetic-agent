# hermetic_agent 部署指南 (docker compose)

统一 compose `docker-compose.yml` 通过 **`PULL_POLICY`** env-var 在 `local` / `registry` 模式间切换, 用 **`--profile frontend`** 启用 frontend. 单 service 设计, 默认 `docker compose up -d` 即工作.

## 3 个 service, 1 个 compose

| Service | 端口 (host→container) | 角色 | 默认启用 |
|---|---|---|---|
| `hermetic_agent-hub` | `28000→8000` | Hub 主服务 (Sanic, L1-L3) | ✅ |
| `opencode-1` | `24096`, `27778` (调试) | opencode sandbox 容器 (L4) | ✅ |
| `hermetic_agent-frontend` | `23000→13000` | nginx 反代 + 静态 (L0) | ❌ (`--profile frontend`) |

要 N 个 sandbox 节点就复制 `opencode-1` 块, 改 `hostname: opencode-N` 即可 (container_name 默认由 compose 生成).

## 4 种启动组合

| 模式 | 命令 | 镜像来源 |
|---|---|---|
| `local` (默认) | `docker compose up -d --build` | 本地 Dockerfile 构建 (`:dev` tag) |
| `registry` (生产) | `PULL_POLICY=always docker compose up -d` | registry pull (用 `HERMETIC_AGENT_*_IMAGE`) |
| `local` + frontend | `docker compose --profile frontend up -d --build` | 本地 + frontend |
| `registry` + frontend | `PULL_POLICY=always docker compose --profile frontend up -d` | registry + frontend |

## 模式命名 (跟 `docker compose` 命令不冲突)

- **`local`** — 本地 Dockerfile 构建
- **`registry`** — 从 registry 拉镜像
- 这两个名字**不**跟 `docker compose build` / `docker compose pull` 子命令冲突

## PULL_POLICY 详解

`pull_policy` 是 compose spec 核心字段 (不是 BuildKit extension), 跟 service 的 `image` + `build` 一起决定容器启动时怎么取镜像:

| 值 | 行为 | 适用 |
|---|---|---|
| `missing` (默认) | 本地有就用, 没才拉 (跟"先 `docker compose build`"的工作流匹配) | local 模式, dev |
| `never` | 永远不拉, 缺镜像报错 | 严格离线 |
| `always` | 总是从 registry 拉, 忽略本地 | registry 模式, 生产 |
| `if_not_present` | 等价 `missing` | — |

每个 service 同时声明 `image:` + `build:`:
- `image` 决定 tag
- `build` 决定怎么构建
- `pull_policy` 决定是否拉

## 镜像 tag 映射

| 服务 | local 默认 tag | registry 覆盖 env var |
|---|---|---|
| Hub | `hermetic_agent:dev` | `HERMETIC_AGENT_HUB_IMAGE` |
| opencode sandbox | `opencode-sandbox:dev` | `OPENCODE_SANDBOX_IMAGE` |
| frontend | `hermetic_agent-frontend:dev` | `HERMETIC_AGENT_FRONTEND_IMAGE` |

## 常用命令

### 启动 / 停止

```bash
# local 模式启动 (后台, 走本地 build)
docker compose up -d --build

# 停止 (保留容器, 可 docker compose start 重启)
docker compose stop

# 停止 + 删除容器 + 网络 (保留 named volume opencode-1-runtime)
docker compose down

# 彻底清理 (含 named volume, runtime overlay 也没了)
docker compose down -v

# 重启单个 service (改 .env / scenario YAML 完事)
docker compose restart hermetic_agent-hub

# 重启所有 (按依赖顺序)
docker compose restart
```

### 重新构建

```bash
# 改 src/hermetic_agent/**/*.py → 重建 Hub 镜像 (用 BuildKit cache, 增量 ~9s)
docker compose build hermetic_agent-hub

# 改 work/scenarios/*.yaml → 不需要重建, 重启 Hub 即可 (scenario loader 走 ro bind)
docker compose restart hermetic_agent-hub

# 改 work/sandbox/policy.opencode-1.json → 不需要重建, 走 admin API /admin/policy
curl -X POST http://localhost:27778/admin/policy -H 'Content-Type: application/json' \
    -d '{"agent":{"model":"MiniMax-M2.7-highspeed"}}'

# 强制重建 (忽略 cache, 适用于 Dockerfile 改了)
docker compose build --no-cache hermetic_agent-hub

# 拉取所有镜像 (registry 模式)
PULL_POLICY=always docker compose pull

# 拉取指定镜像
PULL_POLICY=always docker compose pull opencode-1
```

### 单个 Dockerfile 手动 build (不进 compose)

```bash
# Hub 镜像 (从项目根)
docker build -f docker/hermetic-agent/Dockerfile -t hermetic_agent:dev .

# opencode sandbox 镜像
docker build -f docker/opencode/Dockerfile -t opencode-sandbox:dev .

# frontend 镜像 (VITE_BACKEND_URL 是 build-arg)
docker build -f docker/frontend/Dockerfile \
    --build-arg VITE_BACKEND_URL=/api \
    -t hermetic_agent-frontend:dev .

# 推送到 registry
docker tag hermetic_agent:dev ghcr.io/your-org/hermetic_agent-hub:1.0.0
docker push ghcr.io/your-org/hermetic_agent-hub:1.0.0

# BuildKit 显式 cache (跨 build 共享, 慢网环境有用)
DOCKER_BUILDKIT=1 docker buildx build \
    -f docker/hermetic-agent/Dockerfile \
    -t hermetic_agent:dev --load \
    --cache-from type=local,src=/tmp/hermetic_agent-cache \
    --cache-to type=local,dest=/tmp/hermetic_agent-cache,mode=max \
    .
```

### 日志

```bash
# 跟所有 service 日志 (Ctrl-C 退出)
docker compose logs -f

# 跟指定 service
docker compose logs -f hermetic_agent-hub

# 跟指定 service 最近 100 行
docker compose logs --tail=100 hermetic_agent-hub

# 带时间戳
docker compose logs -f -t hermetic_agent-hub
```

### 调试

```bash
# 进容器 shell
docker compose exec hermetic_agent-hub bash
docker compose exec opencode-1 bash

# 单次命令
docker compose exec hermetic_agent-hub python -c "from hermetic_agent.config.settings import get_settings; s = get_settings(); print(s.opencode_base_url)"

# 看进程 / 资源
docker compose top
docker compose stats

# 看 healthcheck 状态
docker compose ps
```

### 验证

```bash
# Hub
curl http://localhost:28000/ready

# opencode
curl http://localhost:24096/global/health

# admin
open http://localhost:27778/docs  # swagger UI

# frontend
curl http://localhost:23000/
```

## 必要的挂载

| 路径 | 类型 | 来源 | 用途 |
|---|---|---|---|
| `${WORKSPACE_PATH}` ↔ `${WORKSPACE_PATH}` | bind rw | host | sandbox 实际工作目录 (host 跟容器同路径, agent 透明) |
| `${SKILLS_SHARED_DIR}` ↔ `/work/shared/skills` | bind ro | host | 中央 skill 源 |
| `opencode-1-runtime` | named volume | docker | `/tmp/opencode-sandbox` 持久化 admin API 写的 runtime overlay |
| `/tmp` `/root/.config` `/root/.local` `/root/.npm` `/root/.cache` | tmpfs | — | 容器内 read_only FS 下的可写点 |
| `/var/cache/nginx` `/var/run` `/var/log/nginx` `/tmp` (frontend) | tmpfs | — | nginx 写目录 |
| `./.env` | env_file | host | Hub 全部配置 (pydantic-settings) |
| `./work` (Hub 内 `/app/work:ro`) | bind ro | host | scenario YAML + shared docs/skills/mcp |

## 端口对照

| 端口 | 用途 | 调试期是否暴露 host |
|---|---|---|
| `28000` | Hub HTTP API (Sanic) | ✅ |
| `8000` | Hub 容器内端口 | — |
| `23000` | frontend nginx | ✅ |
| `13000` | frontend 容器内端口 | — |
| `24096` | opencode serve | ✅ (调试用) |
| `7777` | sandbox health_server | ❌ (容器内) |
| `27778` | sandbox admin_server | ✅ (调试用) |

生产环境把 `opencode-1.ports` 段 + `hermetic_agent-frontend.ports` 段注释掉, sandbox/frontend 不直接对外.

## 调试期: 改 model / key 不 rebuild 镜像

走 admin API (容器内 :7778, 走 Hub 代理: `:28000/agent/admin/opencode/opencode-1/...`):

```bash
# 改 model
curl -X POST http://localhost:27778/admin/policy \
    -H 'Content-Type: application/json' \
    -d '{"agent":{"model":"MiniMax-M2.7-highspeed"}}'

# 改 key
curl -X POST http://localhost:27778/admin/env \
    -H 'Content-Type: application/json' \
    -d '{"OPENAI_API_KEY":"sk-xxx"}'

# 触发 reload (SIGTERM opencode, supervisor 1s 重启, 读新 config + env)
curl -X POST http://localhost:27778/admin/reload
```

## Troubleshooting

### Opencode 报 `ProviderModelNotFoundError`

**3 个最常见原因 + 1 行诊断**:

```bash
# 跑全部 3 项检查 (source + container cfg + 实际 chat):
python scripts/verify_opencode_config.py
```

3 项都 OK 才能保证 chat 真的 work. 任何一项失败脚本会打印**精确修复命令**.

**3 个最常见原因**:

1. **老容器在跑老 `render_config.py`**: 你改了源码但没 `--no-cache build + --force-recreate`. 修法脚本会提示.
2. **opencode 1.16→1.17 升级**: 新版内置 `minimax` provider 跟我们的 `openai` provider 撞了. 修法: 升级后跑 `docker compose build opencode-1 --no-cache` (新版本里 render_config 已正确写 `provider.<name>.models` 列表).
3. **session 缓存**: opencode 内部缓存 session-level model 解析. 跨版本升级后老 session 报 ProviderModelNotFoundError. 修法: 让 client 发新 session id (前端清 session_storage).

**为什么 modelID 日志里带 `openai/` 前缀**: opencode log 显示的 `modelID` 是 `cfg["model"]` 字段的**字面值** (MiniMax-M2.7-highspeed), 不是实际发到上游的值. opencode 内部拆 prefix 后, 实际发到 `OPENAI_BASE_URL` 上游的是裸 `MiniMax-M2.7-highspeed`. `suggestions` 列表里就是无前缀的 known models, 印证上游认无前缀.

**手动 1 项检查** (脚本拆开跑):

```bash
python scripts/verify_opencode_config.py --source         # 只查源码
python scripts/verify_opencode_config.py --container-only  # 只查运行中容器 cfg
python scripts/verify_opencode_config.py --chat-only       # 只跑 chat smoke test
```

### Frontend 容器循环重启, 日志报 `chown ... client_temp ... Operation not permitted` 或 `setgid(101) failed`

**原因**: nginx 官方 entrypoint + master 进程 (root) 启动 worker 前需要 chown + setuid/setgid 到 nginx 用户 (uid 101). 容器需要的能力:

| 操作 | 需要 capability |
|---|---|
| `chown 文件 给其他 uid` | `CAP_CHOWN` |
| `setuid(101)` | `CAP_SETUID` |
| `setgid(101)` | `CAP_SETGID` |

`cap_drop: [ALL]` 会把上面 3 个全丢, 即使 root 也无法完成 → 容器循环重启. 此外 `read_only: true` + tmpfs 挂 `/var/cache/nginx` 会让 image 里的子目录被遮蔽, chown 走到不存在的路径.

**修法** (docker-compose.yml 里已经做了):

1. **不开 `read_only: true`** — 让容器根 FS 可写
2. **`cap_drop` 显式列出**要丢的, 保留 CHOWN/SETUID/SETGID/DAC_OVERRIDE:
   ```yaml
   cap_drop:
     - SYS_ADMIN
     - SYS_MODULE
     - SYS_RAWIO
     - SYS_PTRACE
     - SYS_BOOT
     - NET_RAW
     - SYS_TIME
     - SYSLOG
     - MKNOD
     - AUDIT_WRITE
     - SETFCAP
   security_opt:
     - no-new-privileges
   ```
3. **`docker/frontend/entrypoint.sh`** pre-create nginx 写目录子目录 (image 层目录被 tmpfs 遮蔽, 容器启动时是空 tmpfs):
   ```
   /var/cache/nginx/{client,proxy,fastcgi,uwsgi,scgi}_temp
   /var/run/nginx.pid
   /var/log/nginx
   ```
4. **端口 mapping 改 `23000:13000`** (不是 `13000:3000`, nginx 配的就是 13000)
5. **healthcheck 加 `--timeout`** 防止 wget hang 90s

### `pull_policy: ${PULL_POLICY:-build}` 报 "此处不需要值 ..."

**原因**: 你的 compose 版本不接受 `pull_policy: build` (这是 BuildKit extension, 不是 compose spec 核心值). 老的 docker-compose v1 / Windows Docker Desktop / 老 v2 版本都会拒绝.

**修法**: 用 spec 核心值, 默认 `missing` (= 本地有就用, 没才拉 — 跟 `build` 行为一致). 改 `PULL_POLICY=always` 触发 registry 模式.

### Port 23000 已被占用 (`bind host port 0.0.0.0:23000/tcp: address already in use`)

**原因**: 宿主机上跑了别的进程占着 23000.

**修法**: `ps aux | grep <port>` 找到进程, `kill <pid>`. 或者改 compose 端口映射: `ports: - "23100:13000"` (改 host 侧端口, 容器内仍是 13000).

## 已删除的旧文件 (refactor 2026-06-10)

- `docker-compose.image.yml` → 合并到主 compose (用 `image:` 字段 + `PULL_POLICY=always`)
- `docker-compose.frontend.yml` → 合并到主 compose (用 `--profile frontend`)
- `docker-compose.image.env.example` → 合并到 `.env.example`
- `docker-compose.frontend.env.example` → 合并到 `.env.example`
- `work/sandbox/ask_user.py` (第 3 份 ask_user 副本) → 删除 (docker/ + tests/test_ask_user_script.py 仍保留)
- `.env` / `.env.example` 里的 dead env (`POLICY_FILE`, `WORKSPACE_CONTAINER_PATH`, `OPENCODE_NODES`, `ROUTING_STRATEGY`) → 删除
