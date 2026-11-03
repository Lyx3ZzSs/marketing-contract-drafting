# ONLYOFFICE Docs 10.0 本地转换验证

日期：2026-11-02。当前状态：按用户后续明确要求，项目默认 PDF 转换器已替换为 ONLYOFFICE Docs 10.0，已删除原 LibreOffice 转换代码、配置项、镜像依赖和相关单元测试。下方 WPS 对照是保留的已知版式差异，不表示本次切换消除了这些差异。

## 当前本机混合模式验证

2026-11-02，应用已切换为本机 FastAPI、Vite、Celery worker 和 scheduler；Docker 仅运行 PostgreSQL、Redis、ONLYOFFICE Docs。日常通过 `make up / stop / restart / status` 管理。下方容器应用接入记录为此前阶段的历史证据。

- 已将原预览卷中的 1 个 PDF（276654 字节）复制到 `.local/previews/`，SHA-256 一致，重启后再次核对通过。数据库、字体及 Docs 数据卷沿用原配置。
- 本机 worker 调用真实 Docs 的完整预览烟测通过：10 页、277991 字节、端到端 1.769 秒；覆盖字段绑定、去重、存储、PDF 读取、下载权限、SSE 完成事件和原模板不变。结果见 `native-preview-smoke.json`。烟测 API 使用进程内测试身份，运行中的 API 认证保持启用。
- 本机 OA 只读查询成功取得 1 条候选和 3 条项目明细。预览与转换器相关测试 19 项通过。
- 四个本机进程重启成功；重复 `make up` 保持原 PID，没有启动第二套进程。

## 正式接入与本地回归（此前容器模式）

- 后端使用 `app.pdf_converter.convert_pdf`，直接调用 `/converter/from-file`；启用 JWT、唯一转换 key、异步轮询、超时检查、32 MB 输出限制与明确失败提示，无旧转换器回退。官方接口依据：[File upload request](https://api.onlyoffice.com/docs/docs-api/additional-api/conversion-api/request-from-file)。
- API、任务、字段绑定、PDF 存储和下载权限流程保持原接口。缓存指纹增加 `onlyoffice-10:` 固定前缀，默认渲染版本为 `onlyoffice-10.0-v1`，避免复用旧引擎产物。
- 本机 Compose 启动独立 Docs 服务，后端使用容器网络地址；原独立验证容器已停止。中文字体与 WPS 字体迁入 `.local/onlyoffice/fonts` 并只读挂载，字体不纳入源码。测试服务器 Compose 配置已同步，但本轮未连接或部署远程服务器。
- 后端镜像构建成功，实际检查 `soffice` 可执行文件不存在；应用代码、脚本、当前部署说明及环境示例中已无旧转换器引用。历史对照记录保留。

本地前端已启动于 `http://127.0.0.1:15173`，API、Docs、PostgreSQL 和 Redis 健康，worker 实际响应 ping。前端 HTTP 200，未认证模板请求返回 401。已重建并启动 API、worker、scheduler 的最终镜像。

### 实测结果

| 项目 | 结果 |
|---|---|
| Python lint / format / mypy | 通过 |
| 后端单元测试 | 117 项通过 |
| 数据库 / API 预览回归 | 3 项通过（转换注入，涵盖失败重试、去重、权限、过期清理） |
| 实际 Docs 错误密钥 | 正确拒绝，应用报告鉴权失败 |
| 原真实合同通过新应用转换器 | 9 页，368755 字节，1.629 秒 |
| 原真实合同迁移前后版式 | Poppler 96 DPI 下全部 9 页像素一致，见 `integrated-pixel-comparison.json` |
| 实际 Celery → Docs → 存储链路 | 通过，2.267 秒；已适配采购模板加虚构验收数据，生成 10 页 |
| PDF 下载 | 可读取，页数与预览相同，禁止编辑权限生效；下载未覆盖预览文件 |
| 字段结果 | 提取确认 63600 / 10900 / 10500，总额 85000.00、大写捌万伍仟圆整及验收名称 |
| 模板与临时数据 | 原模板字节不变；任务终态清除 DOCX 快照，烟测数据库记录与预览存储文件已清理 |

`backend/scripts/preview_smoke.py` 使用进程内 TestClient 的显式测试身份，向真实 Redis/Celery worker 提交任务；没有给运行中的 API 增加免登录入口。它覆盖字段绑定、去重、转换、读取、下载权限、SSE completed 和原件不变；未覆盖浏览器登录与 PDF.js 交互，也未调用 OA。`preview-smoke.json` 保存结果，`integrated-preview-contact.png` 为 10 页渲染总览。原真实合同与烟测采购模板是两个不同样本，9 页和 10 页不能互作页数比较。

产物（相对项目根目录）：`output/pdf/onlyoffice-integrated-real-contract.pdf` 为原真实合同输出；`output/pdf/preview-smoke.pdf` 和 `preview-smoke-download.pdf` 为虚构字段的测试副本，不作正式合同。

复现原真实合同转换（读取项目 `.env`）：

```bash
backend/.venv/bin/python scripts/verify_onlyoffice.py /absolute/path/to/contract.docx output/pdf/verification.pdf
```

复现完整链路需要已启动的 API、worker、Docs、数据库和 Redis，且 API 与 worker 共用预览目录：

```bash
make up
mkdir -p .local/preview-verification
cd backend
uv run python -m scripts.preview_smoke /absolute/path/to/supported-template.docx ../.local/preview-verification
```

## 切换前的 WPS 一致性验收记录

验收以用户确认的“转换后与 WPS 保持一致”为准，不要求修饰模板。模板允许标题落在页尾、允许跨页拆行，不能作为两端排版不同的验收豁免，也不能据此断言差异完全由模板造成。

## 同源 WPS 对照结果（切换前）

本轮在解锁后的本机 WPS 中打开真实合同的字节副本，使用“输出为 PDF”、普通 PDF、全部 1–9 页、无水印导出。导出后复核 DOCX 的 SHA-256 仍为 `9311a75eb896351d493b1901852a6fd702ad06b913e7a4ab1366f481cf954d52`，与 ONLYOFFICE 已验证输入相同。新 PDF 取代历史 PDF 作为本轮基准，排除了旧对照文件无法证明同版同源的问题。

| 检查 | 本机 WPS 新导出 | ONLYOFFICE（已安装 WPS 字体） |
|---|---|---|
| 总页数 | 9 | 9 |
| 页脚内容 | 共9页第1页至第9页 | 相同；不代表字体和位置完全一致 |
| “正文”标题 | 第 3 页顶部 | 第 2 页尾 |
| 软件表格跨页位置 | 第 4 行“自动上报功能”处 | 第 3 行“超短期模型”处 |
| “三、甲方义务” | 第 4 页 | 第 5 页 |
| “七、验收标准及品质保证” | 第 5 页 | 第 6 页 |
| “十一、保密” | 第 7 页 | 第 8 页 |
| 封面表格高度 | 126.8 pt | 74.8 pt |
| 主要中文字体 | HYShuSongErKW、HYZhongHeiKW | SimSun、SimHei-Bold |

已渲染并查看全部 9 页总览，以及封面和第 3 页表格放大对照。封面表格位置、行高、部分文字换行及后续章节分页确有可见差异，不能以总页数相同判定通过。WPS 新导出仍使用之前未找到完整字体文件的 HYShuSongErKW、HYZhongHeiKW；“安装 WPS 安装目录中的 9 个字体”不等于匹配 WPS 实际字体映射。现有证据尚不能量化字体与排版引擎各自的贡献。

ONLYOFFICE 最近单次转换耗时为 1.081 秒；WPS 本轮通过桌面界面导出，未做精确计时，不作速度倍数比较。真实合同没有页眉，不能用本样本声称已完成真实复杂页眉一致性验证。结论仅适用于本机 macOS WPS 与当前 Docs 10.0 环境。

证据：`wps-same-source-comparison.json` 保存源文件 hash、两份 PDF hash、字体、页脚、章节页码及表格几何；`wps-same-source-contact.png` 为全部页面并排图；`wps-same-source-cover.png`、`wps-same-source-table.png` 为放大图。PDF 分别位于 `output/pdf/wps-same-source-contract.pdf` 和 `output/pdf/onlyoffice-real-contract-wps-fonts.pdf`（均相对项目根目录）。

下一步应围绕 WPS 实际使用字体及映射做受控验证，再检查剩余引擎差异。无需将修改原模板分页规则作为替换的前置要求；在这些同源差异消除前，不能承诺转换后与 WPS 一致。

## WPS 字体安装及同源验证（2026-11-02）

已将本机 `/Applications/wpsoffice.app/Contents/Resources/office6/fonts/` 下全部 9 个 TTF 文件复制至独立验证容器的 `/usr/share/fonts/truetype/custom/wps/`，执行 `documentserver-generate-allfonts.sh` 完成索引重建及服务重启。该目录位于当前容器的持久化字体卷，重启后保留；重新创建容器时应复用该卷或重新安装。未改共享字体目录内已有文件，未改真实 Word、分页规则、项目转换实现或远程环境。验证容器本轮结束后保持运行，地址 `http://127.0.0.1:18082`。

`wps-font-manifest.json` 记录 9 个文件的 SHA-256 与字体内部名称。方正书宋、方正仿宋、汉仪楷体简、汉仪旗黑、汉仪中简黑均已进入字体索引；独立测试文档显式引用这 5 款字体，输出 PDF 确认全部嵌入。视觉证据见 `wps-font-smoke.png`。字体原文件未改名或伪装为其他字体。

真实合同保持同一 SHA-256，使用新的转换 key 重新生成：

- 输出 `output/pdf/onlyoffice-real-contract-wps-fonts.pdf`，9 页、368755 字节，服务索引重建后复测耗时 1.081 秒。
- 安装前后输出的字体列表相同；逐页以 Poppler 96 DPI 渲染，9 页像素完全一致，详见 `wps-font-comparison.json`。PDF 文件 hash 因时间等元数据不同而不同，不代表可见内容变化。
- 标题仍落在第 2 页尾，表格仍在相同位置断页；仅添加这些字体没有改善本样本版式。
- 进一步提取字体实际对应字符：`Noto Sans KR-Bold` 用于 14 个顿号，`TakaoPGothic` 用于“壹、捌”两个字。后两个字在 DOCX 中直接指定微软雅黑，本次 WPS 字体包不包含微软雅黑。不能因看到替代字体名称就推断大段正文使用了日韩字体。
- 原对照 PDF 中的 `HYShuSongErKW`、`HYZhongHeiKW` 仍未在当前字体索引发现。新增汉仪字体不应被描述为已完整补齐原 PDF 的同款字体。

结论：可取得的 WPS 字体安装成功且可用于转换；同源样本版式没有变化。此实验只证明“加入本机这 9 个 WPS 字体文件”没有改变结果，不能外推为任何字体环境都不会影响排版。后续若需复现原 WPS 排版，还需确认实际字体文件与匹配策略，并复核同源输出；是否修改模板由业务要求决定。

重新安装当前字体集：

```bash
docker exec marketing-contract-onlyoffice-validation mkdir -p /usr/share/fonts/truetype/custom/wps
docker cp .local/onlyoffice-validation/wps-fonts/. marketing-contract-onlyoffice-validation:/usr/share/fonts/truetype/custom/wps/
docker exec marketing-contract-onlyoffice-validation /usr/bin/documentserver-generate-allfonts.sh
```

## 原因诊断与单变量验证（2026-11-02）

在同一真实样本、同一服务和字体环境下重新转换，稳定复现标题在第 2 页、引言在第 3 页，以及“超短期模型”一行被拆开的现象。仅修改临时副本中的单项分页策略，未改原件及应用模板。

| 实验 | 标题与引言同页 | 目标单元格内容在一页内 |
|---|---|---|
| 原始 DOCX 重跑 | 否（2 / 3 页） | 否（3 / 4 页） |
| 只给“正文”段添加 `w:keepNext` | 是（均第 3 页） | 是（前文高度变化带来的附带结果） |
| 只给标的表各行添加 `w:cantSplit` | 否（仍为 2 / 3 页） | 是（整行移至第 4 页） |

源 XML 证据：“正文”是普通段落，仅直接设置居中、加粗和字号；没有标题样式、`keepNext`、`pageBreakBefore` 或自身分页符，继承的 Normal 样式也没有与下段同页设置。标题之前有空段落。标的表行没有 `cantSplit`，行高未设为 `exact`；封面表格没有显式行高。因此，文档允许引擎依据实际排版结果决定换页和行高，没有编码“正文必须与后文同页”和“标的行不得跨页”的要求。

已确认的直接原因是缺少这两项分页约束，添加相应约束后 ONLYOFFICE 能正确执行。`heading-keep-next.png` 和 `table-no-split.png` 保存单变量实验的视觉证据。这证明症状可以由规则消除，但不证明全部版式差异都由缺少规则导致。

字体方面：原始对照 PDF 嵌入 HYShuSongErKW、HYZhongHeiKW、PingFangSC-Regular 等，本次结果使用 SimSun、SimHei-Bold，并出现 Noto Sans KR-Bold、TakaoPGothic。两端字体环境不同，可能改变换行和高度；目前没有控制字体单变量的实验，不能量化其贡献，也不能把它认定为所有分页差异的唯一原因。

证据边界：旧 PDF 的来源元数据是 WPS/Quartz，尚无导出时 DOCX 的 hash，无法严格证明同版同源；精确断页位置差异中的字体、引擎和版本因素尚未完全分离。本次诊断针对上述真实采购合同，不自动代表项目全部模板。

规则语义：[Microsoft KeepNext](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.keepnext)、[Microsoft CantSplit](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.cantsplit)。原件和正式转换实现保持原状。

## 环境与样本

- Docker ARM64，`onlyoffice-documentserver 10.0.0-169`，端口 `127.0.0.1:18082`，开启独立 JWT。
- 官方 ARM64 manifest：`sha256:22fc0082188a4785f0b66a47d7d8bbc84af1031837e45f8e951c777aaf957c6b`。
- 只读挂载本机既有 ONLYOFFICE 中文字体目录。没有修改原字体、Word 原件、应用代码或远程部署。
- 真实样本：`/Users/liyuanxin/Desktop/sprixin/合同比对/正式合同/营销中心/2/凯力、旭皖能源、双环、和安分布式光伏电站分布式功率预测系统V1.0采购合同主.docx`。
- DOCX SHA-256：`9311a75eb896351d493b1901852a6fd702ad06b913e7a4ab1366f481cf954d52`，3 张表格、281 个段落。
- 对照为同目录 `original_凯力、旭皖能源、双环、和安分布式光伏电站分布式功率预测系统V1.0采购合同主.pdf`：WPS/Quartz 输出，9 页。它是已有业务对照文件，不是本次以相同字体重新生成的 Microsoft Word 基准。

## 结果

| 检查 | 实测 |
|---|---|
| 转换接口 | `/converter/from-file`，JWT、异步上传及轮询正常，返回有效 PDF |
| 耗时 | 三次独立 key：1.071、1.585、1.046 秒；中位数 1.071 秒。包含 HTTP 上传、0.5 秒轮询等待、结果接收；不含镜像下载、容器启动，不代表并发性能 |
| 文件 | 368755 字节，PDF 2.0，9 页 A4 |
| 金额 | 提取确认 118000、70800、47200、29500；这不是对全部业务内容逐字一致的证明 |
| 页脚 | 逐页提取并核对“共9页第1页”至“共9页第9页” |
| 字体 | PDF 嵌入 SimSun、Times New Roman、SimHei-Bold，同时出现 Noto Sans KR-Bold、TakaoPGothic 等替代字体；未完成逐 run 字体映射归因 |
| 跨页表格 | 第 3–4 页连续，金额和行内容可见；断页点与对照不同，软件表第 3 行被拆到两页，对照在更后位置断页 |
| 版式差异 | “正文”标题位于第 2 页底部，对照在第 3 页顶部；封面表格行高明显缩小；部分后续章节所在页面变化 |
| 页眉 | 真实样本没有页眉。另在测试副本加入“页眉兼容性验证（测试副本）”，9 页均能提取，首页面貌检查正常；只覆盖简单默认页眉，不证明复杂分节、奇偶页或图片页眉兼容 |

已查看全部 9 页缩略图、重点查看第 3–4 页表格和页眉首面。源文件未修改。项目另一份协议虽然存在 header XML 部件，但部件全部为空，因此未把它计为有效页眉验收样本。

## 证据与复现

- `onlyoffice-contact.png`：转换结果 9 页总览。
- `reference-contact.png`：既有业务 PDF 总览。
- `header-proof.png`：显式标记的测试副本页眉。
- `../../../output/pdf/onlyoffice-real-contract.pdf`：真实合同转换结果，存在上述版式差异，仅用于评估。
- `../../../output/pdf/onlyoffice-header-sample.pdf`：增加测试页眉的副本，不能用于正式业务。
- 相邻 JSON 保存输出 hash、源文件 hash 和单次耗时。测试副本源 hash 与真实原件不同是预期行为。
- `scripts/verify_onlyoffice.py` 提供独立复现入口；服务 JWT 保存在被 Git 忽略的 `.local/onlyoffice-validation/server.env`，不写入报告。

```bash
docker start marketing-contract-onlyoffice-validation
backend/.venv/bin/python scripts/verify_onlyoffice.py /absolute/path/to/contract.docx output/pdf/verification.pdf --env-file .local/onlyoffice-validation/server.env
```

该轮验证没有修改转换实现。之后按用户明确指令执行了切换，当前部署与回归结果见本文开头；旧独立验证容器已停止，历史资料保留。

## Univer 对当前需求的适配

官方 Docs 功能表支持页眉页脚、页码和跨页表格，但明确 PDF 输出需要打印模块与浏览器 Save as PDF，没有独立服务端 PDF 转换 API。因此它可以作为未来在线编辑器候选，当前不能直接替代 `convert_pdf(bytes) -> bytes`。DOCX 导入导出和打印属于 Pro 扩展，不能将开源核心等同于完整转换链路。

来源：[Docs 功能表](https://docs.univer.ai/overview/features/docs)、[导入导出](https://docs.univer.ai/guides/docs/features/import-export)、[打印](https://docs.univer.ai/guides/docs/features/print)、[仓库中文说明](https://github.com/dream-num/univer/blob/dev/docs/readme/zh-CN.md)。本次没有运行 Univer 实测。
