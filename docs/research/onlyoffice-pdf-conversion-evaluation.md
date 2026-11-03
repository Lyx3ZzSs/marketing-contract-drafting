# ONLYOFFICE 替换 LibreOffice 的可行性评估

日期：2026-11-02。依据：当前项目源码与 ONLYOFFICE 官方文档。本轮没有安装 ONLYOFFICE、转换实际合同、修改应用或部署配置。

## 结论

技术上可行，建议使用 **ONLYOFFICE Docs 10.0 或更新版本的 Conversion API** 替换后台 DOCX → PDF 环节。保留现有 Word 字段回填、Celery 任务、PDF 存储、PDF.js 阅读器和下载权限处理。新增一个本地 ONLYOFFICE 服务即可，前后端仍可以在本机运行；无需将整个应用迁入容器，也不必嵌入在线编辑器。

这是代码与接口层面的可行性结论；是否比当前方案更接近 Microsoft Word 排版，需要用本项目合同样本验证，不能由“支持 DOCX”推导出分页完全一致。

## 接口选择

Docs 10.0 新增 `POST /converter/from-file`：以 `multipart/form-data` 上传 DOCX，完成后直接返回转换文件字节。异步请求用固定 `key` 和参数轮询，后续请求可省略文件；处理中返回 JSON，完成后返回 PDF。启用 JWT 时，转换参数取自 token，payload 必须包含 `operation: "converter"`，且不能包含 `url`。这与项目现有 `bytes → bytes` 边界匹配，无需新增让 ONLYOFFICE 拉取合同的下载接口。[官方文件上传转换接口](https://api.onlyoffice.com/docs/docs-api/additional-api/conversion-api/request-from-file)

更老版本使用 `/converter` 接口，需要提供可由服务访问的源文件 URL。若公司已有旧版实例，必须补充临时文件访问和结果下载流程，改动更多。[传统转换接口](https://api.onlyoffice.com/docs/docs-api/additional-api/conversion-api/request)

## 项目改动范围

| 位置 | 建议改动 |
|---|---|
| `backend/app/pdf_converter.py` | 保留 `convert_pdf(docx: bytes) -> bytes`，将 `soffice` 子进程替换为 HTTP 上传、异步轮询及二进制响应处理；维持 PDF 签名与 32 MB 限制。 |
| `backend/app/core/config.py`、`.env.example` | 增加服务地址、独立 JWT secret、连接及总耗时配置；更新 `preview_renderer_revision`，避免复用 LibreOffice 的旧缓存。 |
| `backend/app/preview_tasks.py` | 保留现有任务和存储流程；协调当前 120 秒转换预算与 Celery 150/180 秒时限，处理服务不可达、排队、超时、错误响应。 |
| 本地/测试部署与 `backend/Dockerfile` | 配置 ONLYOFFICE 服务、固定版本及字体；迁移验收后移除 LibreOffice 安装项。 |
| 转换测试、README | 替换缺少二进制测试，新增接口错误和超时测试，更新启动及故障说明。 |

`document_previews.py` 已负责生成 DOCX 副本、用户归属和缓存；`preview_files.py` 负责 PDF 存取；`pdf_permissions.py` 负责下载权限。这些能力不需要交给 ONLYOFFICE 重写。HTTP 超时不等于取消服务端转换，必须验证服务端任务和缓存的清理行为。

## 本地运行与替代选项

Docs 有官方 ARM64 Docker 路线，适合在当前 Apple Silicon 本机通过 Docker Desktop 运行独立服务。官方 Docker 通用需求为至少 4 GB RAM、40 GB 可用磁盘；这是部署基线，不代表实际常驻占用。需实测本机资源。[ARM64 安装](https://helpcenter.onlyoffice.com/docs/installation/docs-community-install-docker-arm64.aspx)、[Docker 系统要求](https://helpcenter.onlyoffice.com/docs/installation/docs-community-sys-reqs-docker.aspx)

若目标是完全避免新增常驻服务，ONLYOFFICE Document Builder 可通过 CLI/SDK 做本地转换，并提供 macOS ARM64 包。但当前官方安装文档明确说明免费版本生成文档有水印，去水印及完整功能需商业许可，因此不能直接作为无成本的正式合同输出方案。[Builder 概览](https://api.onlyoffice.com/docs/document-builder/get-started/overview)、[安装与许可说明](https://api.onlyoffice.com/docs/document-builder/get-started/installing)

Docs Community 与商业版本的许可条件不同，具体选择取决于最终集成和使用方式，本文不作法律判断。也不能把旧版“20 个编辑连接”视为转换限额：官方说明 9.4 已移除该连接限制；实际转换吞吐仍需按所选版本、配置和机器测试。[版本比较](https://www.onlyoffice.com/compare-editions)、[9.4 发布说明](https://www.onlyoffice.com/blog/2026/05/onlyoffice-docs-9-4)

## 验收重点

1. 使用当前已确认模板及填充后的合同副本，核对中文字体、金额大小写、表格跨页、页眉页脚、长名称、备注和黄色高亮清除。字体文件与版本必须固定，不能假设容器自动具备宋体、楷体。
2. 验证预览、更新预览、下载 PDF、权限限制及原模板不变；切换引擎后缓存必须失效。
3. 验证无效 JWT、转换错误、超限、服务断开与超时的错误提示；响应 JSON 不能误存为 PDF。[官方错误码](https://api.onlyoffice.com/docs/docs-api/additional-api/conversion-api/error-codes)
4. 用实际合同测单任务耗时、并发排队、内存与磁盘占用，并核对转换服务的临时文件保留/清理。

建议先完成一份真实合同的本地转换对照，再替换项目默认引擎。当前评估未证明版式改善，也未测得运行资源或吞吐数据。
