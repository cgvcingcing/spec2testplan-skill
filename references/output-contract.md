# 内部设计数据与输出契约 v3

JSON 使用 UTF-8，字段名和枚举为英文，正文默认中文；Python 3.9+，仅标准库。证据和设计 JSON 是临时校验数据，默认交付由 `doc-to-html` 转换的 HTML。JSON 仅在明确要求时交付。

## 正文与内部数据

新方案正文为需求简述、测试思路与重点、测试范围、测试模块与对象、测试点与方法。保留一句来源和“设计草稿、未执行”说明。测试思路要回答怎么测、先测什么、为什么重点测；依据已有测试点组织，不抄一份明细。

测试点保留功能、场景、验证内容、关键预期、测试方法、优先级及理由。同类输入、字段、入口和边界归并，保留不同结果。HTML 用分组检查卡片替代长表：P0 和待确认项默认展开，P1／P2 折叠；支持展开全部、重点跳转自动展开、窄屏单列和打印全部内容。折叠只改变阅读状态，不改变点数或内容。待确认项可为 P0，但预期仍为空。

`render` 默认 `--layout html`，生成供 `doc-to-html` 转换的 Markdown／HTML 混合中间稿；Markdown 交付用 `--layout markdown`，输出普通标题和段落，无交互样式及脚本，设计数据相同。

需求台账、追溯编号、指纹、覆盖关联与证据定位渲染为 `spec2testplan-provenance` HTML 注释，不在正文显示。注释保留设计数据和各来源的相对路径、SHA-256、块定位；转换需保留注释。用 `--document-dir` 指定交付目录。正文不另加规则台账、通用策略、准备／完成清单或覆盖矩阵。

## 证据 JSON

`extract` 生成，不手改。`schema_version: 1`；`sources[]` 包含 `id/path/sha256/format/blocks`，路径相对证据文件。块包含 `id/kind/locator/heading/text`，可含图片或链接；`warnings[]` 保留静态提取限制。

## 设计 JSON

新设计使用 `schema_version: 3`。v1／v2 保持原校验与精简渲染，不从旧数据自动推断测试重点或优先级。v1 未分类场景显示“未分类”。

| 顶层字段 | 类型 | 含义 |
| --- | --- | --- |
| `schema_version` | integer | 新设计为 `3` |
| `title` | string | 文档标题 |
| `mode` | string | `outline` 或 `plan`，均保留主线与重点，大纲可简写 |
| `source_fingerprints` | object | 全部来源 ID→SHA-256，原样复制 |
| `overview` | string | 一两段需求简述 |
| `test_approach` | object | 测试主线、建议顺序和有理由的重点，v3 必填 |
| `scope` | array | 范围表的各行 |
| `modules` | array | 测试模块、对象及功能 |
| `requirements` | array | 内部可追溯规则，不单列正文 |
| `test_points` | array | 模块/功能层测试点 |
| `questions` | array | 未定业务问题，可为空 |
| `limitations` | string array | 只写影响范围或预期的材料限制，简短就近展示 |

v2／v3 不要求 `strategy/preparation/completion`；为兼容旧输入可保留，仍校验但不展示。不要新写这些流程台账。v1 字段契约保持原有结构。

### 测试主线、顺序与重点

```json
{
  "summary": "先用有效申请验证创建结果，再对照数量规则拒绝范围外输入，同时核对失败时没有产生记录。",
  "stages": [
    {
      "title": "验证申请提交与规则拦截",
      "intent": "从申请表单与提交服务核对接收和拒绝结果；该入口决定后续是否会产生业务记录。",
      "module_ids": ["MOD-001"],
      "test_point_ids": ["TP-001"]
    }
  ],
  "focus_areas": [
    {
      "title": "非法数量不能产生记录",
      "risk": "若范围外数量仍提交成功，后续记录就会违反明示的数量约束；需同时观察提交结果和记录创建结果。",
      "test_point_ids": ["TP-001"]
    }
  ]
}
```

- `summary` 用业务语言描述具体测法，不能只写“功能测试、边界测试、异常测试”。
- `stages` 为有序非空数组；每项的 `title/intent/module_ids/test_point_ids` 必填。`intent` 说明本阶段怎么测以及先后的依赖或理由；对象由模块关联展示。所有模块至少在一阶段出现，允许跨阶段复用。`test_point_ids` 选代表性入口检查，须属于本阶段模块，不要求重复罗列该模块所有点。
- `focus_areas` 为非空数组；每项的 `title/risk/test_point_ids` 必填。`risk` 说明本次改动可能造成的具体错误及观测办法；关联点已有证据，不再造一份需求或测试点。无关性能、并发、权限等不借此追加。
- 阶段、重点数量随需求复杂度取舍。优先级及测试顺序属于测试设计判断，不声称是原文规定或已经验证的缺陷。顺序可以因前置依赖先处理 P1；高影响但口径不清的 P0 需先确认。

### 范围

```json
{
  "id": "SCP-001",
  "name": "申请入口及数量校验",
  "coverage": "included",
  "boundary": "覆盖提交与数量约束；输入格式细节待确认。",
  "module_ids": ["MOD-001"],
  "basis": "derived",
  "evidence": ["SRC-001-B0003"],
  "question_ids": []
}
```

`coverage`：`included/excluded/pending`。included 至少关联一模块；excluded 不关联测试模块；pending 必须关联问题。每个模块须属于 included 或 pending 的范围。`basis` 为 `explicit/derived/suggested`，前两者需证据。不要用“未提及”推断业务确定排除；必要时标待确认或说明本次材料未覆盖。

### 模块

```json
{
  "id": "MOD-001",
  "name": "申请提交",
  "objects": ["申请页面", "申请提交服务"],
  "functions": ["数量校验", "有效提交"],
  "requirement_ids": ["REQ-001"],
  "evidence": ["SRC-001-B0003"]
}
```

对象与功能非空，名称取自材料或按业务作用归纳；不是最小函数/字段清单。每个声明功能必须有测试点；点引用的需求必须属于其模块。证据至少包含一条所关联需求依据。

### 内部需求

```json
{"id":"REQ-001","summary":"申请数量为 1～5，含上下限。","status":"clear","evidence":["SRC-001-B0003"]}
```

`status` 为 clear/partial/conflict。partial/conflict 必须关联问题；conflict 解决前不能产生 ready 点。无冲突的部分可独立拆需求。例中数字仅为虚构演示，不可带入实际业务。

### 测试点

```json
{
  "id": "TP-001",
  "module_id": "MOD-001",
  "function": "数量校验",
  "scenario_type": "negative",
  "title": "数量范围外",
  "requirement_ids": ["REQ-001"],
  "evidence": ["SRC-001-B0003"],
  "basis": "derived",
  "method": "边界值分析",
  "preconditions": [],
  "action": "检查上下限外相邻值 0、6。",
  "expected": "两者均不满足数量规则，拒绝提交。",
  "status": "ready",
  "question_ids": [],
  "priority": "P1",
  "priority_reason": "数量边界直接影响规则拦截，需在有效申请链路之后验证。"
}
```

- v2／v3 用 `module_id/function/scenario_type` 替代 v1 `area`。scenario_type 为 positive（正常有效业务）、negative（不满足规则/非法输入）、exception（依赖故障/异常数据/中断等）。不要仅按标题猜类别。
- 所有示例字段必填。`function` 必须在模块 functions 中，`method` 用适合该检查的测试设计方法。
- `action` 简写验证内容；关键条件仅写已知项，避免每行重复账号/环境。可合并一类边界，expected 写清不同结果，避免逐平台逐字段机械扩张。
- basis 为 explicit/derived/suggested，每点至少引用关联需求的一条依据。
- ready 必须有具体 expected，question_ids 为空；needs-confirmation 必须 expected=null 且关联非空问题。suggested 点一律 needs-confirmation。
- v3 的 `priority` 必须为 P0／P1／P2，`priority_reason` 必须有具体影响理由；正文展示。P0 为核心链路或关键结果，P1 为重要分支／边界／联动，P2 为较局部的补充回归。按影响判断，不把页面展示一律降级或所有点都标 P0；无需强凑三档。
- v1／v2 继续允许 `unassigned` 和空理由，保持历史渲染行为。升级旧方案必须人工赋值；脚本只校验结构，不推断业务风险。

### 问题

```json
{"id":"Q-001","question":"输入为空时如何处理？","reason":"只说明数量范围，未写格式约束。","requirement_ids":["REQ-001"],"evidence":["SRC-001-B0003"]}
```

问题关联具体需求及上下文。未确认预期在相应表格中直接显示问题；不另建长篇问题章节。纯环境/人员/工期准备默认不转成业务测试点。已明确验收预期与已知实现缺陷可以同时记录，不能把实现缺陷误当预期未知。

## 编号与兼容

SCP/MOD/REQ/TP/Q 各自唯一，至少三位数字。内部覆盖关联用于检查遗漏，不向用户输出“100%覆盖”或执行通过率。v1 的覆盖计算保留供兼容校验，正文不输出矩阵。

v1 兼容条目 `strategy/preparation/completion` 使用 text/basis/evidence/question_ids 结构；explicit/derived 需证据，suggested 可无。新产物不要求也不生成这些数组。
