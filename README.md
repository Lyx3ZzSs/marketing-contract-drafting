# 营销合同起草系统脚手架

面向国能日新营销侧的开发基础工程。默认首页按已确认的青绿色原型展示基本信息、条款信息与附件信息，保留原系统布局。项目字段初始为空，可按 OA 流水号读取场站名称和合同金额；附件列表为空；合同类型从后台模板库加载，条款由上传的 Word 模板解析而来。支持表单输入、页签与条款目录切换，以及只读条款展示。合同保存、整单删除和提交尚未实现，首页已移除这三个按钮；模板管理入口位于合同类型选择框旁，标题栏下直接显示信息页签。附件操作尚未接入业务接口，点击只显示说明；附件列表没有实际文件。独立的 `/dev` 页面用虚构风电项目验证编辑器、后台工作流、持久化任务和 SSE；不生成正式合同、不连接真实 CRM、不调用大模型。

## 技术组成

- 前端：Vue 3、Vite、TypeScript、Tailwind CSS v4、shadcn-vue、Tiptap、Pinia、Vue Router。
- 后端：FastAPI、Pydantic、SQLAlchemy、Alembic、LangGraph。
- 服务：PostgreSQL 17、Redis 7、Celery、公司已有 MinIO（S3 协议）。
- 工具：Node.js 24、pnpm 11.25.0、Python 3.12、uv。精确依赖见 `pnpm-lock.yaml` 与 `uv.lock`。

## 一键运行

需要可用的 Docker Engine 与 Docker Compose 2.24+。首次构建需要访问镜像和软件包仓库。

```bash
cp .env.example .env
make up
```

访问：

| 服务 | 地址 |
| --- | --- |
| 合同前端原型 | http://127.0.0.1:15173 |
| 工程联调页 | http://127.0.0.1:15173/dev |
| 服务连接检查 | http://127.0.0.1:15173/dev/connections |
| API 文档 | http://127.0.0.1:18400/api/docs |
| 存活检查 | http://127.0.0.1:18400/api/v1/health/live |
| 就绪检查 | http://127.0.0.1:18400/api/v1/health/ready |

Compose 项目名称为 `marketing-contract-scaffold`，PostgreSQL 和 Redis 分别使用本机端口 15432、16379，不复用其他项目容器。端口仅绑定本机。API、worker 与 scheduler 共用镜像；独立迁移容器完成 Alembic 升级后再启动应用。

```bash
docker compose -f deploy/compose.yaml ps
docker compose -f deploy/compose.yaml logs -f api worker
make down
```

`make down` 保留数据库与 Redis 数据卷。不要在需要保留生成记录时执行 `down -v`。

## 本机开发

使用 Node.js 24 和 Python 3.12。安装 pnpm 11.25.0 与 uv 后：

```bash
make install
make infra
make migrate
```

分别在三个终端运行：

```bash
make api
make worker
make web
```

本机 worker 使用 `solo`，便于 macOS 调试；Compose 使用两个工作进程。本机配置读取根目录 `.env`。Compose 覆盖数据库和 Redis 地址为容器内部主机名，其余配置沿用 `.env`。

首页 `ContractShell.vue` 从模板 API 加载合同类型和条款。空白字段定义与列表类型位于 `frontend/src/data/contract-form.ts`，页面拆分在 `frontend/src/components/contract/`，样式位于 `frontend/src/styles/contract.css`。表单与各条款 JSON 通过 Pinia 在当前页面会话中保留，刷新后恢复空白表单及模板原文。合同标的表仅保留软著名称、硬件金额、软件+服务金额、其他软件+服务金额、备注五列；查询合同编号后按 OA 项目明细逐行回填，备注可手工输入并保留在当前会话。重新查询、修改编号或刷新页面会清空备注；尚未接入合同保存。开发联调入口与首页分离。设计依据见 `docs/design/`，视觉核对记录见 `design-qa.md`。

## OA 合同会签取数

首页的合同编号输入框旁提供“查询”，也支持 Enter。这里的合同编号按 OA **流水号** 查询，首尾空格去除后精确匹配；不按 OA 的其他合同编号字段匹配。

| 页面 / 关联 | OA 来源 | 处理规则 |
| --- | --- | --- |
| 合同编号 | `formmain_3396.field0055` | 精确查找，不自动选择重复流水号 |
| 主从关联 | `formson_3398.formmain_id = formmain_3396.ID` | 按 `sort, ID` 读取全部项目明细 |
| 合同名称 | `field0238` 场站名称、`field0445` 场站编码、`field0140` 省份 | 主体名建议＋所选模板的固定封面文字；自动回填，可直接手工修改 |
| 金额 | `formson_3398.field0385` | 全部明细用 Decimal 汇总，不去重金额，返回两位小数字符串 |
| 币种 | `formson_3398.field0485` | 枚举 ID 映射为人民币、美元或欧元 |
| 软著名称 | `formson_3398.field0384` | 每条项目明细一行，按 `sort, ID` 排序，不按名称合并 |
| 硬件金额 | `formson_3398.field0233` | 精确两位小数字符串 |
| 软件+服务金额 | `formson_3398.field0234` | 精确两位小数字符串 |
| 其他软件+服务金额 | `formson_3398.field0291` | 精确两位小数字符串 |
| 备注 | 当前会话手工输入 | 不读取或写回 OA |

合同标的随同基本信息一次查询回填，金额空值显示“—”，零值显示“0.00”，负值保留；分项字段不改变上方 `field0385` 合计。每页可显示 10 或 20 条，翻页保留备注。查询失败、切换编号或等待覆盖确认期间不展示旧标的。

存在多条会签时弹窗列出记录标识、发起日期和原始会签状态，由用户选择；当前不按会签状态过滤。合同名称保持可编辑，手工名称不会自动被建议覆盖。金额只读，零值和负值按原值保留并提示核对。无会签、无明细、缺少金额或币种时明确报错，不把缺失金额当作零。缺少场站名、模板封面未配置或简称建议不可用时，名称独立提示，不阻断有效金额、币种和合同标的回填。

修改编号会取消旧查询、清除旧金额、币种和自动取得的名称，保留手工名称；过期响应不能覆盖新编号。查询不改变合同类型或条款。回填结果只保留在当前页面会话，尚未实现合同保存、提交或 OA 写回。

币种映射来自用户提供的 `项目合同台账枚举映射表20261021.xlsx`，`币种!A2:C4`。后端 `app/oa_enums.py` 保存该版本的三项枚举及源文件 SHA-256，ID 全程使用整数或字符串。OA 读取每条项目明细的币种 ID，再映射名称；这不是在线读取枚举字典表。后续 OA 增加币种时需要同步映射。未知 ID、空币种或同一会签下混合币种均提示核对，不回退人民币，也不自动选择第一条。页面币种只读，查询前为空。

金额仍按已确认的 `field0385` 汇总，始终为人民币口径；接口 `amount_currency` 固定为 `CNY`，与来自 OA 的合同 `currency` 分开。页面及覆盖确认弹窗明确标注人民币金额，不读取或换算 `field0486` 外币金额。

在根目录 `.env` 配置 `OA_HOST`、`OA_PORT`、`OA_DATABASE`、`OA_USER`、`OA_PASSWORD`；参考 `.env.example`。使用仅具 SELECT 权限的账号。应用通过独立 MySQL 连接池和只读事务访问 OA，主表和项目明细在同一读取事务内取得；不会修改 OA 数据、表结构或索引。密码仅在后端环境中使用，错误响应不返回数据库异常或连接参数。

`OA_CONNECT_TIMEOUT` 默认 3 秒；`OA_QUERY_TIMEOUT` 默认 5 秒用于 MySQL 查询超时，驱动同时限制网络读取时间。浏览器等待最长 20 秒。为避免静默截断，超过 100 条候选或 10000 条项目明细会报错。该查询走 REST，不通过 Celery、LangGraph 或 SSE。

| 接口 | 用途 |
| --- | --- |
| `GET /api/v1/oa/contracts/lookup?contract_number=流水号` | 返回匹配会签；大整数记录标识以字符串传输 |
| `GET /api/v1/oa/contracts/{record_id}/project-summary` | 返回项目明细、场站名称、精确金额合计及缺失/异常提示 |

缺少配置时接口返回 503“OA 数据库未配置”。`health/ready` 的 `integrations.oa` 仅报告配置是否完整，连接可用性以实际查询为准。修改环境变量后须重新创建 API 容器；修改后端代码或依赖后执行：

```bash
docker compose -f deploy/compose.yaml up -d --build api
```

当前核实的表结构见 `docs/oa-schema/`。流水号字段未建索引；本轮没有更改 OA 索引，未来若取数变慢应由 OA 管理方评估。该功能沿用本机开发访问边界。

## 后台合同模板管理

模板管理页显示上传区和模板列表。“返回合同起草”返回当前会话，保留 OA 查询结果、标的备注、已选模板及条款草稿；同一模板保留原来的条款目录位置。如果管理期间删除了选中模板，返回时会刷新模板列表并重新选择可用模板。点击模板名称或“预览条款”打开右侧抽屉，左侧目录切换条款，右侧只读展示正文和批注。关闭按钮、Esc 或点击遮罩可关闭抽屉，管理页地址与列表状态保留；上传成功不会自动展开正文。旧独立预览地址返回模板管理页。

点击“上传模板”可直接打开文件选择窗口；也可以点击文件控件的“选择文件”。选好文件后自动上传，无需再点一次按钮。上传失败时可点击“上传模板”重试当前文件，或重新选择文件。

访问 `/admin/templates`（合同类型选择框旁“管理模板”入口），选择 `.docx` 文件即可上传，模板名称可选填；留空时使用去掉扩展名的文件名（最多 200 字符）。上传成功后可以预览条款、下载原始 Word，或点击“删除”并确认后移除模板原文件及条款。模板在合同起草页的“合同类型”中选择。列表为空或 API 不可用时显示明确状态，前端没有本地 JSON 回退。相同文件重复上传返回 409；不同文件可以作为新模板上传，不覆盖原记录。

目前模板原文件（BYTEA）、名称、SHA-256、上传时间和解析条款（JSONB）都保存在 PostgreSQL 的 `contract_templates` 表中，通过 Alembic `0002` 创建；Docker 数据卷保存这些记录，API/前端重启后仍存在。由于公司 MinIO 尚未配置，本阶段模板使用数据库存储，不向 MinIO 上传，也不创建 bucket。该管理入口已接入统一身份认证，仅 `agent_admin` 可上传、删除和配置模板；已获应用权限的用户共享读取模板用于起草。

模板上传限制为 10 MB，解压后最多 40 MB。后端保留正文文字、普通段落、基本强调格式、规则表格和横向合并单元格；批注单独展示。存在独立“正文”段落时从此处解析，否则从文档开头解析；目录识别中文编号、“第 N 条”及 Word 一级/二级标题。无标题时作为一个正文目录项展示。按 Word 最终正文视图排除删除修订，保留所有占位值与备选条款，原文件不修改。图片、自动编号、纵向合并或嵌套表格等暂不支持的正文结构会明确拒绝上传，不会静默丢弃内容。网页不承诺 Word 页码与分页排版保真。

| 接口 | 用途 |
| --- | --- |
| `GET /api/v1/templates` | 模板摘要列表，不返回原文件或条款大字段 |
| `POST /api/v1/templates?name=名称&filename=文件名.docx` | 原始 DOCX 二进制请求体上传，解析及校验成功后事务保存 |
| `GET /api/v1/templates/{id}` | 模板信息与条款内容 |
| `GET /api/v1/templates/{id}/file` | 下载原始 Word 文件 |
| `DELETE /api/v1/templates/{id}` | 删除模板记录、原文件及条款，已不存在时返回 404 |

新环境执行数据库迁移后模板列表为空，需要通过管理页上传。此工作区现有采购模板已通过上传接口导入，前端源码不再携带模板正文。合同页面编辑使用当前会话草稿，不反写模板库，也未实现合同保存；刷新后重新从后台模板原文加载。

前端 `/api` 由 Vite 转发至 API。`/dev` 编辑器内容通过 Pinia 在路由切换间保留，刷新浏览器后重置。关闭页面仅断开 SSE，不取消已提交的后台任务。

## 运行链路与接口

```text
Vue / Tiptap → POST 示例任务 → PostgreSQL queued + 初始事件
                              ↓
                         Redis / Celery
                              ↓
                         LangGraph 示例流程
                              ↓
                        PostgreSQL 状态 + 事件
                              ↓
Vue ← EventSource / SSE ← FastAPI 查询持久化事件
```

LangGraph 执行“校验内容 → 读取示例项目 → 整理结果”；Celery 负责在后台运行它。任务传递 ID，输入从数据库读取。示例结果包含 `source: demo` 和 `model_used: false`。

| 方法与路径 | 行为 |
| --- | --- |
| `GET /api/v1/health/live` | 进程存活，不检查外部依赖 |
| `GET /api/v1/health/ready` | 检查数据库迁移、Redis 与 MinIO bucket 可访问性 |
| `POST /api/v1/demo/tasks` | 接收 `document`（Tiptap JSON）与 `simulate_failure`，返回 202 和任务 ID |
| `GET /api/v1/tasks/{id}` | 返回状态、结果、错误和时间 |
| `GET /api/v1/tasks/{id}/events` | 按顺序发送持久化任务事件 |

事件类型为 `progress`、`completed`、`failed`，都有 `id` 和 JSON `data`。首次连接可用 `?after=事件ID`；浏览器自动重连使用 `Last-Event-ID`，该 header 优先于 query。前端按事件 ID 去重，终态主动关闭连接；已消费完终态的订阅返回 204，停止自动重连。空闲连接每 10 秒发送注释心跳。单次数据库读取结束即释放连接，不长期占用连接池。

任务状态及事件在同一事务中提交。任务执行失败、参数不合法、入队失败有明确反馈。错误统一为 `{"error":{"code":"...","message":"...","request_id":"..."}}`，响应包含 `X-Request-ID`，日志为 JSON。

本阶段没有分布式事务 outbox 或 worker 崩溃后的任务接管。已接入 company-dev 统一认证，生产 Realm 尚未配置。进程在入队/执行过程中被强制终止可能留下 queued/running 任务；已完成任务与事件可在服务重启后继续查询。演示接口仅用于本地开发，不应直接开放为生产服务。

## 公司 MinIO

本项目不启动 MinIO，不创建 bucket，不修改公司存储策略。仅连接已有的专用测试 bucket：

```dotenv
S3_ENDPOINT=minio.example.internal:9000
S3_BUCKET=your-existing-test-bucket
S3_REGION=us-east-1
S3_ACCESS_KEY=your-test-access-key
S3_SECRET_KEY=your-test-secret-key
S3_USE_TLS=true
S3_VERIFY_TLS=true
```

`S3_ENDPOINT` 不带 URL 协议前缀。容器中的 `localhost` 指容器自身；如果存储服务位于宿主机，Docker Desktop 可使用 `host.docker.internal`。密钥只放 `.env` 或运行环境，不进入前端。

未配置 MinIO 时 readiness 会显示 `unconfigured`，不阻断编辑器和示例任务。配置后访问失败会使 readiness 返回 503。Redis 连通不代表 worker 可用，需要用示例任务确认执行。

实际读写验证：

```bash
make storage-smoke
# 或仅使用容器运行
docker compose -f deploy/compose.yaml exec api python -m scripts.storage_smoke
```

脚本在 `scaffold-smoke/` 下创建唯一测试对象，验证内容后删除；启用版本控制的 bucket 会删除本次上传的具体版本。未配置返回 `skipped`；读写或清理失败返回非零退出码。不访问其他对象。

## 检查与测试

```bash
make check
make integration
cd frontend
pnpm exec playwright install chromium
pnpm test:e2e
```

如已安装 Google Chrome，可使用 `E2E_CHANNEL=chrome pnpm test:e2e`，无需额外下载 Chromium。

- `check`：Python lint/format/typecheck、单元测试，前端 lint/typecheck/单元测试/构建，Compose 配置校验。
- `integration`：真实 HTTP/worker 测试需通过环境变量 `TEST_ACCESS_TOKEN` 提供有效管理员 Access Token；未提供时明确跳过。需要运行中的 API、worker、PostgreSQL、Redis；验证成功与失败任务、事件重放、非法游标、心跳及断线不取消任务。测试只清理自己创建的任务。
- `e2e`：需要运行中的前后端，并通过环境变量 `E2E_USERNAME` / `E2E_PASSWORD` 提供管理员测试账号完成真实登录；不提供时跳过，不将凭据写入源码。验证 Tiptap 编辑与导航保留、真实 worker 的成功与失败反馈，以及断线期间任务完成后的事件补取和去重。测试产生的示例任务保留在开发数据库中。
- `storage-smoke`：独立的 MinIO 读写验证，未配置不代表通过。

服务重启验证：先运行工作台任务并记录 ID，再执行 `docker compose -f deploy/compose.yaml restart api worker`，调用任务详情与 events 接口，确认结果和事件仍存在。

## Nginx 联调

先生成前端静态产物，再启动可选 gateway：

```bash
cd frontend && pnpm build
cd ..
docker compose -f deploy/compose.yaml --profile gateway up -d gateway
```

访问 http://127.0.0.1:18088 。配置为 SPA 路由提供回退，并关闭 `/api` 的缓冲和缓存以保证 SSE 及时送达。此配置用于验证静态部署方式，正式内网域名、TLS 尚未配置。统一认证仅注册了 `http://127.0.0.1:15173`，18088 网关入口不能直接登录；需先为实际网关地址注册回调、退出地址和 Web Origin，并修改 `OIDC_FRONTEND_URL`。

## 后续边界

真实 CRM API、字段含义及多项目生成范围仍待确定。Tiptap 只负责基础内容编辑；不宣称支持原 Word 无损导入导出。已适配的采购模板支持受限字段联动和条款预览，具体边界见下文；Word 在线编辑、模板治理及模型供应商仍待接入；完整 PDF 阅读已实现。用户提供的 Word 和数据字典不会被脚手架修改。

## 封面名称与已确认简称

在 OA 查询完成后，独立请求 `GET /api/v1/oa/contracts/{id}/name-suggestions?template_id=...`。
`project-summary.contract_name` 保留为 null，避免旧客户端误把原始场站拼接当作封面名称。
名称由每个场站的主体名与 `contract_templates.cover_config` 组成，页面拼接展示并允许直接编辑。
当前已确认 Word 原件（SHA-256 `094d95c7471ba6295ca7f0d41fe587518c37d584c410eb398846cd17d62463f8`）配置为 `{主体名}风电站 / 风电场功率预测系统V1.0 / 采购合同`。
其他上传文件不继承此配置，可通过模板管理的“封面名称设置”独立设置（接口 `PUT /api/v1/templates/{id}/cover-config`）。第一版自动提取仅支持“风电站”后缀，其他类型明确提示手工填写。

规则实现于 `backend/app/station_names.py`：按枚举层级匹配完整省市县前缀，并用省份 ID 辅助核对；仅清理末尾类别及明确重复后缀，保留分期、编号和含义不明确的括号。源行政区划快照在 `backend/app/data/oa_regions.json`，带文件 SHA、工作表范围及版本；运行时无需访问用户电脑中的 Excel。平山湖案例为用户确认的限定映射，不推广为删除全部括号的规则。

按场站编码去重，无编码时仅按原始名称在当前合同内去重。不同编码的场站不自动合并。
名称自动回填后可直接在合同名称输入框修改。同一合同重新查询、切换模板时保护手工名称；合同编号变化时清除旧名称，过期响应不能覆盖当前合同。未能生成名称时提示手工填写，不阻断金额、币种和合同标的回填。
已移除名称核对弹窗及确认保存接口。已有 `station_aliases` 数据保留，仅在 OA 原名称未变化时只读复用；直接编辑完整合同名称只保留在当前会话，不更新简称库。OA 始终只读。

模板原件保持不变；已确认采购模板的封面名称已实时联动到条款预览。
执行 `cd backend && uv run alembic upgrade head` 应用 `0003` 迁移；`RUN_INTEGRATION=1 uv run pytest tests/test_cover_names.py -m integration` 验证已有简称读取、源数据变更与模板配置（OA 部分使用隔离测试数据，不写入 OA）。


## 基本信息与条款联动

输入 OA 流水号并查询后，“条款信息”自动显示封面、标的表、合同总额及大写金额；修改名称、备注会同步，无需填充按钮。条款当前全部只读，包括黄色日期及付款比例字段；这些字段保留模板原文。模板管理仅展示字段状态，暂不开放编辑权限设置，后端同样拒绝人工字段修改。基本信息联动继续生效，待业务规则确认后再调整。没有新增合同保存或审批流程。

- 同一软著、各类别单价相同的 N 条项目，汇总成硬件、软件及服务、配套软件三行，各行数量 N。单价不取平均，金额缺失不作零处理。不同软著或单价不能按当前三行模板合并时，明确提示，不生成错误的汇总结果。
- 三类行总价合计与 OA `field0385` 的人民币金额核对；不一致时提示校验错误。币种继续展示 OA 项目币种，合同金额仍为人民币口径。
- 每项备注按项目顺序去重合并，在模板中作为跨三行共用备注。同一会签重新查询保留备注；修改合同编号清空旧备注。
- 未标黄内容不回填，包括合同编号、付款金额及甲方等空位。已明确授权的例外仅为标的表数量、单价、总价、合计与共用备注；材料名称的“硬件”“配套软件”等固定后缀保持原样。

后端分别由 `contract_values.py`（Decimal 汇总和大写）、`contract_document.py`（位置白名单和预览结构）、`contract_drafts.py`（接口及版本校验）负责。前端 `contract-draft.ts` 管理联动、请求取消及过期响应；`BoundDocumentNode.vue` 按后端字段权限渲染，当前全部为只读 DOM。原有完整条款 JSON 草稿机制已移除；开发工作台及模板只读预览仍使用 Tiptap。

接口：`GET/PUT /api/v1/templates/{id}/fields`、`POST /api/v1/templates/{id}/preview`。字段设置存储在 PostgreSQL `contract_templates.field_bindings`；执行 `uv run alembic upgrade head` 应用 `0004` 迁移。版本由原文件 SHA、映射实现版本、字段设置及封面配置共同确定。

当前映射 `wind-purchase-v1` 仅适用于上述 SHA 的已确认原件。其他文件可以上传、预览，但不会猜测金额单元格或套用该文件的位置，须新增并验证相应映射。页面是内容预览，不复制 Word 分页。合同 Word 下载按钮及导出接口已移除；模板管理仍可下载上传的原文件。

联调验收（2026-10-22）：真实 OA 三条标的汇总为三行，数量均为 3，行总价为 190800、32700、31500，合计 255000.00，大写“贰拾伍万伍仟圆整”。已验证备注去重与三行共用、付款比例非法值反馈、模板版本及非许可字段校验。原件保持不变。


## 完整合同 PDF 预览

入口仅在“条款信息”页的页签栏右侧，独立于正文卡片。查询 OA 并取得有效名称、标的及合计后可点击“预览合同”；模板未适配、名称缺失或金额校验不通过时不可生成。条款继续保持只读。预览采用第 3 版浅色全屏阅读器，支持缩略图、连续滚动、页码跳转、缩放、整页显示与适合宽度。没有新增 Word 下载、打印、签章或审批入口。

返回起草保留当前条款目录和会话。修改基本信息后，入口显示“更新并预览合同”；生成成功后恢复页码、页内位置、缩放与侧栏状态。切换合同编号或模板会重置阅读位置。生成中返回不取消后台任务，过期响应不能覆盖新合同。内容未变化时后端按输入快照和渲染版本复用结果。

链路：`当前会话快照 → 共用字段校验和 OOXML 绑定 → Celery → LibreOffice → PDF 存储 → PDF.js`。条款预览与整份 PDF 共用 `prepare_document`，金额与大写不重复计算。原模板字节保持不变，仅在临时副本中替换已授权位置；字段绑定完成后，`package_preview_document` 在 PDF 专用副本中清除黄色高亮（含正文、页眉页脚及样式），其他颜色和格式保留；没有 LLM 调用。PDF 页数来自真实转换结果，不模拟分页。

模块职责：

- `contract_drafts.py` / `contract_document.py`：共用校验、字段绑定与 DOCX 副本封装。
- `document_previews.py`：创建、去重、状态及文件接口；模板版本校验。
- `preview_tasks.py`：任务状态、异常恢复与定时清理；复用现有任务表及 SSE。
- `pdf_converter.py` / `preview_files.py`：独立的转换进程与存储适配。
- `document-preview.ts`：前端生成状态和阅读位置；`ContractPreviewDialog.vue` / `PdfPage.vue` 负责阅读交互、按需渲染及文本选择。

| 接口 | 用途 |
| --- | --- |
| `POST /api/v1/templates/{id}/document-previews` | 提交与条款联动相同的快照，返回预览 ID 和任务 ID |
| `GET /api/v1/document-previews/{id}` | 获取生成状态、错误及 PDF 地址 |
| `GET /api/v1/document-previews/{id}/file` | 内联读取 PDF；未完成返回 409，失效返回 410 |
| `GET /api/v1/document-previews/{id}/download` | 下载当前预览的 PDF，设置禁止编辑权限及中文文件名 |
| `GET /api/v1/tasks/{id}/events` | 复用持久化进度事件，前端另以状态查询补偿断线 |

执行 `make up` 会安装 LibreOffice、开源中文字体并应用 `0005` 迁移。已有运行环境更新：

```bash
docker compose -f deploy/compose.yaml up -d --build api worker scheduler frontend
```

默认 `PREVIEW_STORAGE=local`，PDF 保存到共享 `preview_data` 卷，API、worker、scheduler 使用同一路径，重启不会丢失有效预览。保留期 `PREVIEW_TTL_HOURS=24`；scheduler 每 5 分钟清理过期 PDF、记录和关联任务事件。生成用 DOCX 快照在任务终态后清除。转换默认超时 120 秒，排队或运行超过 10 分钟标记失败，可以重试。修改字体或转换器后应同步增加 `PREVIEW_RENDERER_REVISION`，使旧缓存失效。

本机开发需自行安装 LibreOffice，并将 `LIBREOFFICE_BINARY` 指向 `soffice` 可执行文件；API、worker 和定时清理进程共用 `PREVIEW_DIRECTORY`。定时清理命令：

```bash
cd backend
uv run celery -A app.worker:celery_app beat --loglevel=INFO --schedule=/tmp/contract-preview-beat
```

设置 `PREVIEW_STORAGE=s3` 后使用已有 MinIO 配置，仅操作 `document-previews/` 下生成的对象，不创建 bucket。当前实测使用本地共享卷；MinIO 预览读写未验证。版本控制 bucket 的历史版本保留期应由其生命周期配置管理，应用删除当前对象不会清除旧版本。

容器目前使用 Noto CJK 替代模板中的宋体、楷体等字体。已核对中文、表格、合计与页脚可以正确显示，但 LibreOffice 与 Microsoft Word 的字体度量和排版存在差异，不保证与业务方 Word 的页数完全相同。部署前若要求固定版式，须提供获授权的原字体并用业务样本核对。后台原文件的黄色标记及字段识别规则保留；完整 PDF 预览不显示黄色高亮，未授权空位及正文保持不变，PDF 中不可编辑。

验证记录见 `docs/verification/contract-preview/README.md`。


预览页右上角提供“下载 PDF”，文件名采用当前预览的合同名称。下载读取当前预览快照，不重新查询 OA、不覆盖缓存或后台原模板；预览尚未就绪时按钮不可用，过期及下载错误在预览页内提示。下载副本使用 pikepdf 的 AES-256 权限设置：空用户密码可直接打开，随机所有者密码不对外提供；禁止正文编辑、批注、表单修改及页面重组，允许阅读、复制与打印。这些是 PDF 阅读软件执行的权限标记，不是绝对防篡改或数字签名；原始预览内容不被重排。


## 统一身份认证（2026-10-22）

已按配置验收清单接入 `company-dev` Realm。请使用 **http://127.0.0.1:15173/**，不要替换为 localhost。未登录访问系统会直接跳转统一认证平台，无中间登录确认页。`/callback` 为登录回调，退出后回到 `/` 并自动转到统一认证登录；认证异常停留在错误提示，不自动循环重试。dev 示例域名未注册，不视为可用部署地址。

- 前端：`oidc-client-ts` 通过 Discovery 发现端点，Authorization Code + PKCE S256。Access/Refresh Token 只放内存；sessionStorage 只保留短期登录事务。刷新页面后重新通过统一认证登录，已有 SSO 会话通常无需再次输入凭据。
- 后端：`app/auth.py` 校验 RS256 签名、issuer、exp、aud 包含 `marketing-contract-drafting-api`、Bearer Token 类型和 API Client 下的角色。JWKS 缓存并支持新签名密钥拉取；服务不可用时拒绝授权，不降级放行。业务接口中仅存活探针和公开认证配置无需 Token；API 文档与 OpenAPI Schema 仍可公开读取，不包含凭据或业务数据。
- 身份：使用 `sub`；部门字段允许为空，不推断部门或自行授予角色。前端用户信息与权限来自已验签的 `/api/v1/auth/me`。
- 角色：三种默认角色均可起草、查询和读取共享模板；模板上传、删除、封面/字段配置、原文件下载、服务诊断和示例任务创建限 `agent_admin`。管理层不会自动获得其他用户的预览文件。
- 对象授权：迁移 `0006` 在 tasks 增加 `owner_sub`。任务状态、SSE、预览元数据、PDF 阅读及下载均校验本人或管理员；不提供公开文件链接。预览缓存按 sub 隔离。历史 owner 为空的任务只允许管理员访问。当前无跨用户分享功能。
- OA 查询沿用现有“已获应用业务角色、按合同编号查询”入口；目前没有可靠的 OA 记录到用户/部门权限映射，不依据缺失部门字段推断归属。若需进一步限制可查询的合同范围，需业务提供 OA 数据授权规则。
- SSE 改为带 Authorization 的 fetch 流，断线携带 Last-Event-ID 补取并去重；Token 到期时服务端结束流，客户端刷新后重连。PDF 和模板原文件同样通过带 Token 的 fetch 下载。
- 无 Client Secret 配置项。本系统仅做资源服务器验签，不使用 confidential client 凭据换取机器令牌。验收单中的 Secret 不写入仓库、浏览器或日志。

JWT 时间校验默认允许 5 秒时钟偏差（`OIDC_CLOCK_SKEW_SECONDS`，范围 0–30 秒），适用于签发时间、生效时间和过期时间；仍校验签名、签发方、受众及角色。认证平台与 API 宿主机应同步时间。校验失败日志仅记录异常类型和请求标识，不记录 Token；页面区分过期、时间不同步与无效凭据。

配置见根目录 `.env.example` 的 `OIDC_*` 项。必须使用已注册的实际域名修改 `OIDC_FRONTEND_URL`，不可仅更换浏览器端 URL。

```bash
# 应用资源归属迁移
cd backend && uv run alembic upgrade head
# JWT、角色与跨用户文件隔离测试（使用测试 RSA 签名，不需真实账号）
uv run pytest tests/test_auth.py -q
RUN_INTEGRATION=1 uv run pytest tests/test_document_preview_integration.py -q
```

后台账号密码、统一认证管理 API 及 Keycloak 配置变更不在应用代码中实现。测试不会自动创建用户或修改组织角色。
