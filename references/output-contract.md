# 内部设计数据与输出契约 v2

JSON 使用 UTF-8，字段名和枚举为英文，正文默认中文；Python 3.9+，仅标准库。证据和设计 JSON 是临时校验数据，默认交付由 `doc-to-html` 转换的 HTML。JSON 仅在明确要求时交付。

## 正文与内部数据

正文固定为需求简述、测试范围（表格）、测试模块与对象（表格）、测试点与方法（按模块分表）。保留一句来源和“设计草稿、未执行”说明。

测试点表列：功能、场景、测试点、关键预期、测试方法。同类输入、字段、入口和边界归并，但保留不同结果。待确认预期就近呈现；没有相应业务信号时不凑场景数量。

需求台账、指纹、覆盖关联、完整问题与证据定位用于内部校验，渲染为 `spec2testplan-provenance` HTML 注释，Markdown 和 HTML 中均不显示。注释保留设计数据和各来源的相对路径、SHA-256、块定位；转换需保留注释。用 `--document-dir` 指定交付目录，追溯不依赖临时文件。不要另加规则、策略、准备、完成、矩阵或依据索引章节。

## 证据 JSON

`extract` 生成，不手改。`schema_version: 1`；`sources[]` 包含 `id/path/sha256/format/blocks`，路径相对证据文件。块包含 `id/kind/locator/heading/text`，可含图片或链接；`warnings[]` 保留静态提取限制。

## 设计 JSON

新设计使用 `schema_version: 2`。v1 设计仍可校验并按精简结构渲染，旧数据未分类的场景显示“未分类”；新设计必须明确场景。

| 顶层字段 | 类型 | 含义 |
| --- | --- | --- |
| `schema_version` | integer | 新设计为 `2` |
| `title` | string | 文档标题 |
| `mode` | string | `outline` 或 `plan`，两者均用精简结构 |
| `source_fingerprints` | object | 全部来源 ID→SHA-256，原样复制 |
| `overview` | string | 一两段需求简述 |
| `scope` | array | 范围表的各行 |
| `modules` | array | 测试模块、对象及功能 |
| `requirements` | array | 内部可追溯规则，不单列正文 |
| `test_points` | array | 模块/功能层测试点 |
| `questions` | array | 未定业务问题，可为空 |
| `limitations` | string array | 只写影响范围或预期的材料限制，简短就近展示 |

v2 不要求 `strategy/preparation/completion`；为兼容旧输入可保留，仍校验但不展示。不要新写这些流程台账。v1 字段契约保持原有结构。

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
  "priority": "unassigned",
  "priority_reason": ""
}
```

- v2 用 `module_id/function/scenario_type` 替代 v1 `area`。scenario_type 为 positive（正常有效业务）、negative（不满足规则/非法输入）、exception（依赖故障/异常数据/中断等）。不要仅按标题猜类别。
- 所有示例字段必填。`function` 必须在模块 functions 中，`method` 用适合该检查的测试设计方法。
- `action` 简写验证内容；关键条件仅写已知项，避免每行重复账号/环境。可合并一类边界，expected 写清不同结果，避免逐平台逐字段机械扩张。
- basis 为 explicit/derived/suggested，每点至少引用关联需求的一条依据。
- ready 必须有具体 expected，question_ids 为空；needs-confirmation 必须 expected=null 且关联非空问题。suggested 点一律 needs-confirmation。
- priority 为 P0/P1/P2/unassigned，分配时须有理由。默认 unassigned，正文不渲染优先级。

### 问题

```json
{"id":"Q-001","question":"输入为空时如何处理？","reason":"只说明数量范围，未写格式约束。","requirement_ids":["REQ-001"],"evidence":["SRC-001-B0003"]}
```

问题关联具体需求及上下文。未确认预期在相应表格中直接显示问题；不另建长篇问题章节。纯环境/人员/工期准备默认不转成业务测试点。已明确验收预期与已知实现缺陷可以同时记录，不能把实现缺陷误当预期未知。

## 编号与兼容

SCP/MOD/REQ/TP/Q 各自唯一，至少三位数字。内部覆盖关联用于检查遗漏，不向用户输出“100%覆盖”或执行通过率。v1 的覆盖计算保留供兼容校验，正文不输出矩阵。

v1 兼容条目 `strategy/preparation/completion` 使用 text/basis/evidence/question_ids 结构；explicit/derived 需证据，suggested 可无。新产物不要求也不生成这些数组。
