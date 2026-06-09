# OpenAgent 镜像构建指南

## 缓存策略

`docker/Dockerfile.openagent` 用 **2 阶段 + BuildKit cache mount** 最大化构建缓存:

| 改了什么 | 阶段 A (deps) | 阶段 B (wheel) | 整体耗时 |
|---|---|---|---|
| **首次冷构** | 跑 | 跑 | ~3-4 min |
| 改 `src/openagent/**/*.py` | CACHED | 跑 (~7s) | **~9s** |
| 改 `requirements.txt` / `pyproject.toml` | 失效 (~55s) | CACHED | **~65s** |
| 改 `docker/Dockerfile.openagent` | 全部失效 | 失效 | ~3-4 min |

## 怎么保持缓存

1. **不要改 `requirements.txt` 除非真的换了 deps** — 加个空行/注释也算改, 会触发整层重装
2. **不要改 `pyproject.toml` 的 `[project]` 段** (dependencies / name / version) — 也算改 deps
3. 改 `[project.dependencies]` 时:
   - 改 `pyproject.toml` **同时**改 `requirements.txt` (两文件要保持一致)
   - 加个 CI check 验证一致 (TODO)

## 验证镜像

```bash
# 镜像能装 deps 吗
docker run --rm openagent:dev python -c "import sanic, httpx, pydantic, structlog; print('ok')"

# Hub 能起吗
docker compose up -d openagent-hub
curl http://localhost:18000/ready
```

## Troubleshooting

### `docker compose build` 没用 cache

- 检查 `DOCKER_BUILDKIT=1` (Windows: docker desktop 默认开; Linux shell 加 `export DOCKER_BUILDKIT=1`)
- 看 build log 有 `#N CACHED` 行, 没 CACHED 就是 cache key 变了

### Buildx 显式 cache export (跨 builder)

```bash
docker buildx build \
    -f docker/Dockerfile.openagent \
    -t openagent:dev --load \
    --cache-from type=local,src=/tmp/openagent-cache \
    --cache-to type=local,dest=/tmp/openagent-cache,mode=max \
    .
```

`--cache-to mode=max` 把所有 layer 写进 cache, 不只最终 layer — 让 cache 更密.

## 怎么进一步加速 (按收益排序)

1. ~~拆 deps + runtime 2 阶段~~ ✓ 已做
2. ~~BuildKit cache mount (pip download cache 跨 build 命中)~~ ✓ 已做
3. (可做) 切换到 `uv` — 比 pip 快 10-100x, lock file + cache 全套, 但需引入新工具
4. (可做) `pip install --user` 写到 bind mount, 跨 build 共享 site-packages — 风险大, 跳过
