# 测试服务器部署

- 服务器：`liyuanxin@10.8.8.16`
- 项目根目录：`/home/liyuanxin/marketing-contract-drafting`
- 访问地址：`http://10.8.8.16:15173/`
- Compose 项目：`marketing-contract-test`，与服务器既有服务隔离。

## 目录和配置

源码、部署文件和 `.runtime/` 均在项目根目录。`.runtime/` 不纳入 Git：

| 路径 | 内容 |
| --- | --- |
| `.runtime/test.env` | 数据库密码、OA 连接信息、认证配置；权限 600 |
| `.runtime/postgres` | PostgreSQL 数据与 `log/` 日志 |
| `.runtime/redis` | Redis AOF 数据与 `redis.log` |
| `.runtime/previews` | 合同 PDF 预览产物 |
| `.runtime/tmp` | 应用临时文件 |
| `.runtime/cache` | Celery beat 状态 |
| `.runtime/onlyoffice` | Docs 的字体、数据、转换缓存、日志及内置数据库 |
| `.runtime/logs` | API、worker、scheduler、迁移、Nginx、构建日志 |
| `.runtime/docker-config` | 本项目 Docker CLI 配置 |

经用户明确确认，镜像、容器元数据、构建缓存与 Docker 自身运行日志沿用系统 `/var/lib/docker`。
不修改系统 Docker 配置，不创建项目的 Docker 命名数据卷。

首次准备（数据库密码与 DATABASE_URL 必须一致；使用 `openssl rand -hex 32` 填写 `ONLYOFFICE_JWT_SECRET`；填写实际 OA 参数）：

```bash
cd /home/liyuanxin/marketing-contract-drafting
mkdir -p .runtime/{postgres,redis,previews,tmp,cache,logs/nginx,docker-config,nginx-cache}
mkdir -p .runtime/onlyoffice/{fonts,data,cache,logs,db}
chmod 700 .runtime
cp deploy/test/test.env.example .runtime/test.env
chmod 600 .runtime/test.env
# 编辑 .runtime/test.env 后执行
./deploy/test/manage.sh build
./deploy/test/manage.sh up -d
```

ONLYOFFICE Docs 10.0、PostgreSQL 和 Redis 只在 Compose 网络内部监听，API 也不映射宿主机端口。
唯一网页入口是 Nginx 的 15173；SSE 关闭代理缓冲，SPA 路由支持 callback 回退。
API、worker、scheduler 启动前必须成功执行 Alembic 迁移。
常驻服务设置 `restart: unless-stopped`，Docker 随系统启动后恢复。

## 统一认证

必须在 `marketing-contract-drafting-web` 登记：

- Redirect URI：`http://10.8.8.16:15173/callback`
- Post Logout Redirect URI：`http://10.8.8.16:15173/`
- Web Origin：`http://10.8.8.16:15173`

Keycloak 配置入口：`company-dev` realm → Clients → `marketing-contract-drafting-web`
→ Settings → Access settings。Web Origins 填写来源地址，不附加 `/callback` 或结尾 `/`。
若登录返回后显示 `Failed to fetch`，检查令牌端点的 CORS 响应。`403 / Invalid origin`
表示来源未获允许；登记 Redirect URI 并不会自动登记 Web Origins。修改后重新进入系统发起
新的登录流程，不重复使用旧 callback URL 中的一次性授权码。

测试镜像显式设置 `VITE_ALLOW_HTTP_OIDC=true`。非 HTTPS 浏览器没有原生 `crypto.subtle`，
因此只为 PKCE 的 SHA-256 摘要补充 `@noble/hashes` 实现；随机校验码仍使用浏览器
`crypto.getRandomValues`，授权仍为 Code + PKCE S256，没有关闭 PKCE 或后端 JWT 校验。
该兼容层不提供完整 Web Crypto，也不会将 HTTP 传输变成加密传输。
默认开发构建不开启此选项；HTTPS 下保留原生 Web Crypto。正式部署应使用 HTTPS。

## 运维和验证

```bash
./deploy/test/manage.sh ps
./deploy/test/manage.sh restart api worker scheduler frontend
curl -f http://127.0.0.1:15173/api/v1/health/live
./deploy/test/manage.sh exec api alembic current
./deploy/test/manage.sh exec worker celery -A app.worker:celery_app inspect ping --timeout=5
```

日常日志在 `.runtime/logs`（PostgreSQL、Redis 日志见目录表），需要按磁盘容量定期轮转归档。
Docker 自身日志保留每容器 3 份、每份 10 MB。不要使用 `docker system prune` 清理共享服务器。

更新前备份数据库，备份产物仍存项目内：

```bash
mkdir -p .runtime/backups
./deploy/test/manage.sh exec -T postgres pg_dump -U contract -d contract_drafting -Fc \
  > ".runtime/backups/contract-$(date +%Y%m%d-%H%M%S).dump"
./deploy/test/manage.sh build
./deploy/test/manage.sh up -d
```

只有登录、OA 查询、合同条款联动、PDF 预览/下载均经过真实浏览器验证后，才视为业务验收完成。
MinIO 未配置时使用项目内预览存储，不宣称外部对象存储已验收。

### 2026-10-23 实机验收

- 真实账号统一登录、退出后返回统一认证登录页通过；测试来源的 CORS 已配置。
- OA 查询返回 3 条项目明细、人民币金额 255,000.00 元，条款自动联动。
- Celery 生成 12 页 PDF；浏览器缩略图、分页、下载正常，正式预览无黄色高亮。
- 下载文件无需口令阅读，PDF 权限禁止修改、批注、表单编辑及页面组装，允许打印。
- API、worker 重启后模板、已完成任务和 PDF 可继续读取；匿名访问 PDF 返回 401。
- PDF.js 的 `.mjs` worker 必须以 JavaScript MIME 类型提供，Nginx 已显式配置。

验收状态及截图保存在服务器 `.runtime/verification/`；其中合同 PDF 为验收副本，
正式预览仍按应用的过期清理策略管理。此次未验证 MinIO，使用项目内本地存储。


## 网络受限时的前端构建

如果服务器无法下载 npm 依赖，可在开发机用锁文件构建，再封装镜像；不要启动 Vite 开发服务作为测试入口。

```bash
VITE_ALLOW_HTTP_OIDC=true pnpm --dir frontend build
# 将 frontend/dist 上传至服务器 .runtime/frontend-package/dist
# 将 deploy/test/frontend-runtime.Dockerfile 复制为 .runtime/frontend-package/Dockerfile
./deploy/test/manage.sh -f deploy/test/prebuilt.yaml build
./deploy/test/manage.sh -f deploy/test/prebuilt.yaml up -d --no-build
```

后端测试构建使用 USTC Debian 镜像源，软件包仍经 apt 签名和校验和校验。
默认开发 Dockerfile 仍使用官方 Debian 源。

## 转换服务

worker 通过 `http://onlyoffice:80/converter/from-file` 上传 DOCX，使用与 Docs 一致的 JWT 密钥。`worker` 等待 Docs 健康后启动。将获授权字体放在 `.runtime/onlyoffice/fonts`，重启 Docs 后更新 `PREVIEW_RENDERER_REVISION` 并重建 API、worker 容器。字体不随仓库或镜像分发；缺少匹配字体会改变版式。修改部署文件不代表已更新远程服务器，部署后需用业务样本复验。
