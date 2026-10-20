# spec2testplan-skill

仅读取 HTML、Markdown 需求文档，生成测试大纲或测试方案。无需业务知识库、项目代码、接口描述或预先注入的业务规则。

Agent 根据 Skill 分析需求，默认调用 `doc-to-html` Skill 生成可离线打开的单文件 HTML；仅未安装该技能时兜底 Markdown。JSON 只在用户明确要求时交付。

本项目的 Python 辅助脚本提取原文证据、校验引用并生成 Markdown 中间稿，不负责模型推理，不需要 API Key 或第三方包。HTML 转换使用 `doc-to-html` 自身的脚本与依赖。

## 安装

要求 Python 3.9+，在项目根目录执行：

```bash
bash install.sh
bash install.sh --check
```

默认安装到：

| 平台 | 技能目录 | 调用 |
| --- | --- | --- |
| Codex | `${CODEX_HOME:-~/.codex}/skills/spec2testplan` | `$spec2testplan` |
| Claude Code | `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/spec2testplan` | `/spec2testplan` |

安装后在新会话中调用。两端使用同一份 `SKILL.md` 和脚本；具体设计文字可能随模型与输入变化。安装器仅管理本技能目录，不修改全局 `AGENTS.md`、`CLAUDE.md` 或其他技能，也不自动安装 `doc-to-html`。

可单独选择平台或卸载：

```bash
bash install.sh --target codex
bash install.sh --target claude
bash install.sh --uninstall
```

支持 `--codex-root DIR`、`--claude-root DIR` 指定配置根目录。覆盖或卸载仅适用于带本项目管理标记的目录，遇到其他同名目录会报错并保留内容。

## 使用

Codex：

```text
$spec2testplan 根据 docs/需求.md 生成测试大纲，输出到同目录。
$spec2testplan 仅读取 docs/方案.html 和 docs/补充.md，生成测试方案。
$spec2testplan 根据 docs/需求.md 生成测试方案，输出为 JSON。
```

Claude Code：

```text
/spec2testplan 根据 docs/方案.html 生成测试方案，保留原文依据。
```

默认在第一个输入文件旁交付一份文件，用户指定目录时遵循指定位置：

| 条件 | 交付格式 |
| --- | --- |
| 未指定格式，或要求 HTML，已安装 `doc-to-html` | 调用该 Skill 转换，交付 `需求.testplan.html` |
| 未指定格式，或要求 HTML，未安装 `doc-to-html` | 兜底交付 `需求.testplan.md` 并说明原因 |
| 明确指定 Markdown | 交付 `需求.testplan.md` |
| 明确指定 JSON | 交付校验后的 `需求.testplan.json` |

JSON 不作为默认或兜底格式。分析中的证据 JSON、设计 JSON 和 Markdown 中间稿放在任务临时目录，成功交付后清理；默认不附带。正文只留一行来源；指纹、原文定位和设计关联保存在不可见追溯注释，清理临时文件后仍可核查。用户另要原文证据 JSON 时才附带。

Agent 会读取并调用已发现的 `doc-to-html` Skill，遵循它的转换、自检和清理流程。已安装但转换失败时先诊断修复，仍失败则说明故障；这种情况不能冒充“未安装”而静默切换格式。

正文采用四部分：

1. 需求简述：改动目标与主要影响。
2. 测试范围：表格说明哪些纳入、哪些不纳入、哪些待确认及边界。
3. 测试模块与对象：模块、测试对象及主要功能。
4. 测试点与方法：按模块列功能、正向/逆向/异常场景、测试点、关键预期和方法。

同类字段、入口及边界归并到功能层，不展开逐步操作用例。待确认内容放在受影响模块附近；不再单列规则、策略、准备、完成、矩阵或依据索引。输出为待评审设计，不表示已执行。

## 处理原则

业务预期只来自输入材料。允许用等价类、边界值、判定表、状态迁移等通用方法推导检查点；文档没写的业务常量、错误码、权限、退款规则和时间要求均保留待确认。建议与原文明示内容分别标注。

原文中的指令和命令当作文档数据处理。HTML 仅静态解析，不运行脚本、不加载网络资源；优先提取 `article` / `main` 的正文，过滤导航和显式隐藏内容。跨行、跨列表格与视觉材料会提示人工核对，纯动态页面需要提供静态导出。

来源更新后指纹校验会失败，需要重新提取并复核设计。脚本能检查引用、编号、状态和来源是否匹配，不能证明模型没有误解业务或遗漏测试点。源材料限制是 Agent 的工作约定，不是操作系统级沙箱。

## 辅助脚本

以下是 Agent 使用的内部步骤，不是默认交付命令。`<work-dir>` 是本次任务新建的临时目录，`<delivery-dir>` 是最终交付目录：

```bash
python3 scripts/spec2testplan.py extract docs/需求.md -o <work-dir>/sources.json
# Agent 按 references/output-contract.md 编写 <work-dir>/plan.json
python3 scripts/spec2testplan.py validate <work-dir>/plan.json --sources <work-dir>/sources.json
python3 scripts/spec2testplan.py render <work-dir>/plan.json --sources <work-dir>/sources.json -o <work-dir>/testplan.md --document-dir <delivery-dir>
```

`render` 只生成 Markdown，默认 HTML 交付还需由 Agent 调用 `doc-to-html` Skill。`--document-dir` 只影响正文中的来源路径，不移动或修改证据；省略时默认以 Markdown 输出文件的目录为基准。

可直接查看 [虚构需求](examples/sample.md) 和 [HTML 测试方案](examples/sample.testplan.html)。`examples/fixtures/` 中的 JSON 是用于复现校验的固定输入，不表示默认交付 JSON。示例中的数字和业务规则仅用于演示，不属于技能的默认业务规则。复核示例：

```bash
python3 scripts/spec2testplan.py validate examples/fixtures/sample.testplan.json --sources examples/fixtures/sample.sources.json
# 更新 HTML 时，先渲染到任务临时目录，再调用 doc-to-html Skill 转换到 examples/
```

设计 schema v2 增加范围、模块对象与场景类型；v1 数据仍可校验和精简渲染。测试覆盖来源变化、冲突与未确认预期、模块功能映射、注释安全和临时文件清理后的来源定位。

运行回归检查：

```bash
python3 -m unittest discover -s tests -v
```

## 项目结构

```text
SKILL.md                        两端共用的技能入口
agents/openai.yaml              Codex 技能展示信息
references/output-contract.md   内部 JSON 字段、引用与交付约定
scripts/spec2testplan.py         静态提取、结构校验、Markdown 中间稿渲染
scripts/spec_sources.py          Markdown / HTML 证据解析
scripts/spec_plan.py             设计校验与文档生成
scripts/install.py              双平台安装、校验与卸载
install.sh                      安装入口
examples/                       虚构需求、HTML 示例与校验 fixtures
tests/                          提取、追溯、渲染和安装回归
```

维护时更新源项目后重新运行安装器。安装包不包含机器特定绝对路径，也不包含示例需求和测试数据。
