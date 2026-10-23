# 合同分页预览交互原型（待确认）

独立演示，不连接 OA，不修改现有业务代码，不生成正式 PDF。使用四页 HTML 样张验证阅读和返回修改流程；内容为节选演示，不能当作合同使用。

运行：`npm install` 后执行 `npm run dev -- --host 127.0.0.1 --port 15174 --strictPort`。

## 两个场景

- 正常分页预览：连续滚动、缩略图、页码跳转、上一页/下一页、缩放、整页/适合宽度、返回起草。
- 返回修改后更新：从第 2 页返回基本信息，修改名称及备注（或点“填入示例修改”），点“更新并预览合同”。模拟生成后恢复原页、页内相对位置及缩放模式；版本由 V1 更新为 V2。生成期间可取消返回修改。

所有数据仅在内存中，刷新或切换场景会重置。顶部场景条、示例填充按钮、模拟生成延迟仅用于评审，不进入正式产品。

## 待确认的设计

1. 白纸＋深灰背景、独立工具栏的分页阅读体验。
2. 修改时返回原起草页面；重新预览后恢复阅读位置。
3. 更新提示采用悬浮通知，避免挤压页面或改变缩放。

真正的 DOCX 转 PDF、字体配置、真实分页和缓存链路要在交互确认后另行实施。没有恢复合同 Word 下载功能。

## Selected visual direction (2026-10-22)

The third comparison image is the approved visual direction. The prototype now uses a white thumbnail sidebar, a pale gray document canvas, full-page fit by default, and reading-position restoration after updates. Open http://127.0.0.1:15174/ to test the two scenarios. Updated evidence: `normal-preview-light.png`, `updated-preview-light.png`, `direction-3-comparison.png`, and `design-qa.md`. This change does not touch production frontend/backend code.
