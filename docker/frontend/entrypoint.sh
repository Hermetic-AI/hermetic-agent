#!/bin/sh
# Frontend container init — pre-create nginx 运行时需要的可写子目录.
#
# 背景: 我们用 tmpfs 挂 /var/cache/nginx, image 里的子目录被遮蔽, 是空
# tmpfs. nginx master 进程启动时 chown /var/cache/nginx/{client,proxy,
# fastcgi,uwsgi,scgi}_temp 给 nginx 用户 (uid 101), 路径不存在 → chown
# 失败 → 循环重启.
#
# 修法: 在官方 entrypoint 跑之前, pre-create 这些子目录 + chown 给 nginx.
# 跑完再 exec 官方 entrypoint, 跟原本行为完全一致.

set -e

# pre-create + chown nginx 写目录
for d in /var/cache/nginx/client_temp \
         /var/cache/nginx/proxy_temp \
         /var/cache/nginx/fastcgi_temp \
         /var/cache/nginx/uwsgi_temp \
         /var/cache/nginx/scgi_temp; do
    mkdir -p "$d"
    echo "[frontend-init] mkdir+chown $d"
    chown nginx:nginx "$d" 2>&1
done

# /var/run/nginx.pid (官方 entrypoint 没 chown 这个, nginx 自己写)
touch /var/run/nginx.pid
chown nginx:nginx /var/run/nginx.pid 2>&1

# /var/log/nginx/* (chown 给 nginx, 让 worker 写日志)
mkdir -p /var/log/nginx
chown -R nginx:nginx /var/log/nginx 2>&1

echo "[frontend-init] pre-create done, exec official entrypoint"
exec /docker-entrypoint.sh "$@"
