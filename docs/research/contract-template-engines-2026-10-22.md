# 合同模板动态填充与局部编辑开源方案调研

调研日期：2026-10-22。范围：官方文档、项目仓库和关键生成源码；未安装运行候选项目；只读检查本地原合同模板的 OOXML，未上传内部文件，未改动业务代码。

## 结论

已有可借鉴方案，但需要拆成两项能力：**结构化数据确定性填充 Word**，以及**只允许修改指定字段**。模板引擎通常只解决第一项。黄色是展示格式，不能直接成为后端权限依据；应把黄色区域登记为有稳定 ID 的字段，默认锁定其余内容。

对现有 Vue / FastAPI 架构，优先借鉴 docassemble 的“数据问卷与正文分离”，以 docxtpl 或精确 OOXML 填充处理准备好的模板。不能把完整合同交给 LLM 重写后，依靠提示词保证固定正文不变。

## 候选项目比较

| 项目 | 已核实的实际机制 | 对本项目的参考价值 | 主要边界 |
|---|---|---|---|
| docassemble | Python 问卷变量通过 Jinja2 / docxtpl 合入 DOCX | 数据填写与固定合同文字分离；可借鉴字段补齐流程 | 完整平台，不必替换现有应用；不是黄区局部编辑组件 |
| docxtpl | DOCX 内 `{{ field }}`、条件、表格行循环 | FastAPI 后端直接集成最自然 | 需要规范化模板标签；不是 Word 编辑器或权限引擎 |
| Docxtemplater | Word 占位符、数组循环、条件生成 | Node / 浏览器方案成熟；可借鉴变量检查与错误报告 | 高级模块付费；限制编辑能力不能算开源核心自带 |
| Accord Project | TemplateMark + 结构化数据 → AgreementMark，另转输出格式 | 字段类型、模板正文、合同数据分离 | 不是保留现有 Word XML 的原位填充路径 |
| Clausefill-AI | 检测占位符、AI 辅助问答、手工 XML 替换 | 可借鉴逐个补齐空缺变量的体验 | 仓库标 Inactive；生成源码有合并 run 的格式风险 |

### docassemble

官方支持 DOCX 模板与问卷变量绑定，DOCX 装配主要依赖 python-docx-template；用户通过问卷输入变量，生成文档。这与 OA 取值后只补充缺失字段的需求相近。平台自身是 MIT，依赖各有许可证。本次未发现“识别黄色即自动限制编辑”的内置承诺。[文档装配](https://docassemble.org/docs/documents.html)、[许可证](https://docassemble.org/docs/license.html)

判断：借鉴数据流程即可，整体迁入其问卷平台会增加与现有前端、后台重复的能力。

### docxtpl

通过 `DocxTemplate.render(context)` 回填 Word 中的 Jinja2 标签；段落、表格行、列有专用标签。普通标签不能随意跨 run 或段落；输入中的 XML 特殊字符需要正确转义。支持基于 Word 模板生成并不等于逐像素保真，也不提供黄色区域编辑权限。[官方使用与限制](https://docxtpl.readthedocs.io/en/latest/)

仓库标注 LGPL-2.1，不能把它写成 MIT 或“无任何许可证条件”。本次不作整个应用的法律许可判断。[项目及许可](https://github.com/elapouya/python-docx-template)

判断：适合已有 Python 后端；应先在模板派生副本中把可变区域规范化为命名字段，验证混合样式、表格、分页、页眉页脚，再选用。原件保持不可变。

### Docxtemplater

开源核心支持文本占位、条件和循环，核心按 MIT 或 GPLv3 双许可供选择；支持浏览器与 Node。[标签机制](https://docxtemplater.com/docs/tag-types/)、[核心许可证](https://github.com/open-xml-templating/docxtemplater/blob/master/LICENSE.md)

官方把 HTML、图片、Meta 等列为付费模块。Meta 可设置 readOnly、forms、trackedChanges、comments；forms 只允许表单编辑，并不是直接按颜色识别。官方也说明这种 Word 限制不是加密，保护可以被移除。[模块分类](https://docxtemplater.com/docs/)、[Meta 功能及边界](https://docxtemplater.com/modules/meta/)

判断：可作为 Node 备选；本项目已经使用 FastAPI，不能仅为简单字段替换就认为必须增加 Node 文档服务。浏览器内生成结果也不能替代后端对字段修改范围的校验。

### Accord Project

当前重点参考 `template-engine`，旧 `cicero` 仓库地址会重定向到 `template-archive`。当前引擎将 TemplateMark JSON 和合同数据合成 AgreementMark JSON，再由 markdown-transform 转 HTML、PDF、DOCX；源码 Apache-2.0。[当前引擎](https://github.com/accordproject/template-engine)、[官方示例测试](https://github.com/accordproject/template-engine/blob/main/test/HelloWorld.test.ts)

TemplateMark 变量声明关联 Concerto 类型，支持数字、日期、枚举等数据和条件块。[TemplateMark](https://docs.accordproject.org/docs/markup-templatemark/)

判断：最值得借鉴的是字段类型和文本分离。它的转换链不能作为现有 DOCX 页眉、编号、复杂表格完全不变的证明；当前阶段不建议整体改为 Markdown 合同体系。

### Clausefill-AI

这是直接与 AI 法律模板填空相关的项目，仓库标注 Inactive、AGPL-3.0。README 描述检测方括号、花括号、下划线占位符，并用 AI 辅助生成问题。[仓库](https://github.com/theianmay/clausefill-ai)

核查源码发现：解析端用 Mammoth 取 HTML 与文本，再用正则提取占位符；不是解析黄色高亮。[解析源码](https://github.com/theianmay/clausefill-ai/blob/master/app/api/parse-document/route.ts)

生成端虽导入 Docxtemplater，但实际修改 `word/document.xml`：拼接命中段落文本，把替换后的整段放入首个 run，并删除后续 run。由此可推断，原段落混合字体、黄色区域和其他内联内容存在丢失风险；不能采信 README 的“完美格式”宣传，也没有看到黄色范围白名单校验。[生成源码](https://github.com/theianmay/clausefill-ai/blob/master/app/api/generate-doc/route.ts)

判断：借鉴“识别字段 → 补齐 → 预览”的流程，不复用其生成实现。

## 面向当前需求的建议

以下是结合上述机制提出的设计建议，不是任何候选项目开箱即用的能力。

1. **保存不可变原模板与版本。** 首次录入时识别黄色候选区，由模板配置把它们绑定为稳定字段；后续按字段 ID 定位，不按页面坐标或模糊全文替换。
2. **把来源与可编辑权限分开。** 每个字段分别记录数据来源、类型、默认值、是否允许用户覆盖、重复绑定位置。来自 OA 的值也只有对应黄色字段允许时才能手工改；固定正文即使模型认为不合适也不开放修改。
3. **按数据生成。** OA 返回值经过字段映射和格式化后填入模板；合同金额维持既有人民币口径，币种显示维持既有规则。未绑定或缺少值的黄色字段提示用户补齐，不由模型编造。
4. **前端编辑字段值，固定文字只读。** 保持基本信息和条款导航布局，可在条款正文中放置黄色可编辑控件；固定文本不能粘贴覆盖、拖动删除或被跨区选中后修改。
5. **后端只接受字段补丁。** 接收 `{templateVersion, fieldId, value}` 之类结构，校验允许字段、类型和长度；由服务器可信模板生成最终文件。不要接受完整 HTML / DOCX 正文直接覆盖固定条款。
6. **原 Word 保留链路。** 若选择 docxtpl，准备命名标签派生模板；若黄色区域存在复杂跨 run、表格和内联对象，需要评估精确 OOXML 替换或内容控件路线，不能仅靠普通字符串替换。
7. **文件外的“不可改”单独界定。** 应用内固定正文可由前后端约束保证；下载后的 DOCX 限制编辑主要依赖兼容编辑器遵守，不能宣称防篡改。若需要正式定稿版本，应另定义服务器生成与版本校验规则。

建议下一步用一份真实模板做离线能力验证：盘点全部黄色区域；确认它们是值、整句、表格还是说明；建立字段映射；测试重复字段、多行文本、金额、表格多行、长名称、跨页、页眉页脚和特殊字符。通过后再决定 docxtpl 还是内容控件 / 精确 OOXML 路线。实际模板的黄色范围核查见下一节；尚未执行填充与排版验证。

## 当前模板的只读核查

主 Agent 补充核查：读取原件 `/Users/liyuanxin/Desktop/sprixin/营销合同起草/合同模版/【最新！！！】软著-采购合同（国能日新通用模板）202511.docx` 的 ZIP / OOXML，未修改原件，未上传到外部服务。SHA-256 为 `094d95c7471ba6295ca7f0d41fe587518c37d584c410eb398846cd17d62463f8`，与本项目已知模板指纹一致。本轮做格式结构检查，未做渲染保真测试。

- `word/document.xml` 有 34 个 `w:highlight` 的值为 `yellow`，这表示格式节点数量，不代表 34 个独立业务字段。Word 会把连续文字拆为多个 run。
- `w:sdt` 内容控件数量为 0；`word/settings.xml` 中 `documentProtection` 的 enforcement 为 0，未启用限制编辑。
- 黄色主要是封面场站、反复出现的产品名称、签订日期、总额及大写、四个付款比例。
- 合同编号、甲方与签订地点空位、标的物表的单价/总价/备注空位没有直接黄色高亮；付款比例为黄色，但紧随其后的付款金额与大写不是黄色。
- 同一个产品名称在封面、标题、正文、标的物和服务条款反复出现，应使用同一逻辑字段绑定多个位置，不能按黄色块数量分别录入互不相关的值。
- 金额黄区包含空格、单位和逗号（`0 .00元，`），需要分离数值与固定标点；不要把整段文字随意改成可编辑字符串。

黄色在 Word 中是文本显示格式，而非编辑权限。[Microsoft Open XML Highlight](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.wordprocessing.highlight?view=openxml-3.0.1)

### 需要澄清的模板边界

用户已明确“只有黄色可让用户修改”，因此非黄色区域默认不得手工修改。**是否允许系统自动填写非黄色空位，是另一项配置，不能默认为允许。** 在用户确认之前，不自动回填上述非黄色位置，也不因为内容看起来像占位符而扩大编辑范围。

此前确认封面 `风电站 / 风电场功率预测系统V1.0 / 采购合同` 固定，只有主体名动态。但原件把整段 `xxxxxx风电站` 与产品名称标为黄色。建议把黄色视为候选范围，在模板配置中将场站主体名开放，固定后缀与固定产品文字继续锁定；是否采用这一范围，进入实施前明确。

| 模板位置 | 可用来源或处理方式 | 当前边界 |
|---|---|---|
| 封面主体名 | 现有场站主体名规则与人工输入值 | 只替换主体名，后缀固定；不能将完整合同名称塞入第一行 |
| 标题与正文产品名称 | 模板固定配置，或者未来明确的产品字段 | 当前按此前固定要求处理，不能直接把多条软著名称拼进去 |
| 总金额及大写 | 现有人民币金额 + 确定性金额大写转换 | 不用模型计算，不以外币币种改写人民币总额 |
| 日期 | 用户补填或以后明确的数据来源 | 不自行使用当天日期代替签订日期 |
| 四个付款比例 | 用户填写、数值与合计校验 | 周边付款金额未标黄，是否允许公式回填需明确 |
| 编号及标的物金额 | 现有基本信息和合同标的数据可用 | 目标位置未标黄，需决定系统专用回填区或修订模板字段标注 |

另外，OA 可能返回多个项目，模板标的物表目前是固定三行。三项金额与三行材料的映射、按项目重复还是汇总，必须单独定义；若整张表不允许变更结构，不能擅自循环新增行。

## 在线编辑组件的补充调研

### ONLYOFFICE

官方明确支持文档模式下 `edit:false`、`review:false`、`fillForms:true` 的仅填写模式；需在编辑模式下使用，并关闭不需要的评论及内容控件设置权限。内容控件可设置“不可删除”和“内容不可编辑”，字段有 Tag，可用于绑定。[权限文档](https://api.onlyoffice.com/docs/docs-api/usage-api/config/document/permissions/)、[内容控件](https://helpcenter.onlyoffice.com/docs/userguides/document_editor/InsertContentControls.aspx)

这最接近“在 Word 正文里只能填写指定区域”。必须先把黄色普通文字转换成真实字段，不能给任意标黄 DOCX 配上 fillForms 就假定可用。固定正文限制来自文档的仅填写模式，不是只给黄色控件加不可删除锁。

社区版为 AGPL-3.0；Developer / Enterprise 为商业版本。官方用于外部 UI 实时操纵编辑器的 Automation API 是 Developer 额外付费能力，不能把它当免费社区 API。[版本及许可](https://github.com/ONLYOFFICE/DocumentServer)、[Automation API](https://api.onlyoffice.com/docs/docs-api/usage-api/automation-api/)

建议：若需要 Word 分页、页眉页脚、表格原貌下直接填表，列为优先验证对象；如果只需在现有条款界面填值，现阶段引入整套 Document Server 的收益未必抵得上部署与集成成本。

### SuperDoc

官方文档展示按 Tag 填充内容控件、更新重复出现的同一字段，以及 `sdtLocked`、`contentLocked`、`sdtContentLocked` 等锁模式。锁只约束正常编辑，不承担用户授权；未被控件覆盖的固定正文也不能自动视为已锁。[填写模板](https://docs.superdoc.dev/editor/content-controls/fill-a-docx-template/)、[字段锁](https://docs.superdoc.dev/editor/content-controls/lock-template-fields/)

许可不能只看项目的“开源”标签：官方当前资料明确 SuperDoc 开源代码为 AGPLv3，`@superdoc/docx-engine` 为单独的专有许可组件，不是开源软件。[引擎许可原文](https://docs.superdoc.dev/resources/docx-engine-license/)。本项目若优先选择可完整自主维护的开源方案，暂不把该路线列为首选；未安装测试此组件。

### AI 合同审阅项目的适用边界

Contract Playbook Reviewer 使用 Gemini + SuperDoc 做规则提取、风险分析和修订痕迹。它说明 AI 与文档引擎可以分离，但主要目标是审阅和改写，而非只填黄色字段，不能直接作为本需求的权限方案。[官方仓库](https://github.com/yuch85/contract-playbook-ai)

## 现有工程差距与推荐方向

已只读查看 `backend/app/template_parser.py` 和 `frontend/src/components/contract/ContractClauseEditor.vue`：前者目前只转换粗体、斜体、下划线，未传递黄色高亮、字段身份或编辑权限，且从“正文”开始解析，封面不在现有条款数据中；后者默认整段可编辑，使用 StarterKit + TableKit。因而仅调整高亮 CSS 不能满足要求，不能把当前条款 JSON 当作原 Word 的完整生成来源。

建议保持 Vue / FastAPI 和页面布局，采用下列数据流程：

`OA 查询 → 标准合同字段 → 模板字段映射 → 黄色字段编辑 → 后端字段校验 → 从可信模板生成 DOCX`

原始 DOCX、用于生成的派生模板、字段定义、每份合同的填写数据分别存储并关联模板版本。黄色候选识别只在模板配置阶段使用；配置定稿后按稳定 field ID 与 anchor 定位。来源、系统可写和用户可改三个维度分别定义。首期限制简单文本、日期、百分比、金额，不能默认开放整条法律条款自由编辑。

前端继续左侧条款目录、右侧正文，在黄色位置展示字段控件；固定文字用只读视图呈现。若继续用 Tiptap，需要字段节点及跨范围删除/粘贴的约束，不能只使用 `contenteditable=false`——官方明确这种节点本身仍可能被整体删除。[Tiptap Node views](https://tiptap.dev/docs/editor/extensions/custom-extensions/node-views)。后端只接收字段值，固定正文始终取服务器模板，提交完整 HTML 不能作为生成依据。

首选验证 **docxtpl 规范化模板 + 字段式条款界面**；如果原始黄色范围不适合转标签，再验证带 Tag 的 Word 内容控件与精确 OOXML 填充。两者都应从模板副本生成，保留非目标内容；不能承诺填入任意长度后分页和行高完全不变。需要 Word 级网页排版时再评估 ONLYOFFICE。

AI 可在模板管理阶段建议“这个黄区可能对应哪个字段”，管理员一次确认绑定；运行时对 OA 金额、名称和固定条款实行确定性填充，不需要引入模型。没有开展实现，也没有变动服务、数据库或原模板。

## 后续验证清单

1. 核对所有黄色候选范围，确认是否存在系统可写但用户不可改的非黄色空位。
2. 在派生模板上绑定字段；重复字段统一来源，确认固定后缀和产品名称的边界。
3. 验证单项目、多项目、缺失值、长场站名、特殊字符、人民币大写和付款金额联动。
4. 验证固定正文不能被跨区选中删除、粘贴覆盖、拖动和撤销操作改变；字段 ID 与模板版本不能由客户端伪造扩大范围。
5. 原件与生成件做非目标 OOXML 内容/结构比对，并分别渲染检查表格、分页、字体与页眉页脚。不能把 ZIP 文件字节完全一致当作可行的生成验收。
