"""Validate traceable design artifacts and render reviewable Markdown."""

import html
import json
import os
import re
from pathlib import Path

from spec_sources import SpecError, digest, extract_sources


BASIS = {"explicit": "原文明示", "derived": "方法推导", "suggested": "待确认建议"}
SCENARIOS = {"positive": "正向", "negative": "逆向", "exception": "异常"}
SCOPE = {"included": "纳入", "excluded": "不纳入", "pending": "待确认"}
COMPACT_STYLE = """<style>
.hero-meta{display:none}
.wrap{max-width:1120px;padding:36px 40px 60px}
.content h2{margin-top:32px}
.content h3{margin-top:28px}
.content table:has(th:nth-child(5)){table-layout:fixed}
.content table:has(th:nth-child(5)) th:nth-child(1){width:11%}
.content table:has(th:nth-child(5)) th:nth-child(2){width:7%}
.content table:has(th:nth-child(5)) th:nth-child(3){width:35%}
.content table:has(th:nth-child(5)) th:nth-child(4){width:35%}
.content table:has(th:nth-child(5)) th:nth-child(5){width:12%}
.content table:has(th:nth-child(5)) td{overflow-wrap:anywhere}
.content table:has(th:nth-child(5)) td:nth-child(2){white-space:nowrap}
@media(max-width:760px){.wrap{padding:24px 18px}.content table:has(th:nth-child(5)){min-width:760px}}
</style>"""


def read_json(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SpecError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    with Path(path).open(encoding="utf-8-sig") as stream:
        return json.load(stream, object_pairs_hook=unique_pairs)


def need(condition, message):
    if not condition:
        raise SpecError(message)


def keys(value, required, context, optional=()):
    need(isinstance(value, dict), f"{context}: expected an object")
    missing = set(required) - set(value)
    extra = set(value) - set(required) - set(optional)
    need(not missing, f"{context}: missing fields: {', '.join(sorted(missing))}")
    need(not extra, f"{context}: unknown fields: {', '.join(sorted(extra))}")


def text(value, context):
    need(isinstance(value, str) and bool(value.strip()), f"{context}: expected non-empty text")


def strings(value, context, nonempty=False):
    need(isinstance(value, list), f"{context}: expected a list")
    need(not nonempty or bool(value), f"{context}: cannot be empty")
    for item in value:
        text(item, context)
    need(len(set(value)) == len(value), f"{context}: duplicate values")


def enum(value, choices, context):
    need(isinstance(value, str) and value in choices, f"{context}: expected one of {', '.join(sorted(choices))}")


def references(values, available, context, nonempty=True):
    strings(values, context, nonempty)
    need(set(values) <= set(available), f"{context}: unknown references: {', '.join(sorted(set(values) - set(available)))}")


def indexed(items, prefix, context):
    need(isinstance(items, list), f"{context}: expected a list")
    result = {}
    for item in items:
        need(isinstance(item, dict), f"{context}: entries must be objects")
        identity = item.get("id")
        need(isinstance(identity, str) and bool(re.fullmatch(prefix + r"-\d{3,}", identity)), f"{context}: invalid ID {identity!r}")
        need(identity not in result, f"{context}: duplicate ID {identity}")
        result[identity] = item
    return result


def load_evidence(path):
    path = Path(path).resolve()
    evidence = read_json(path)
    keys(evidence, {"schema_version", "sources", "warnings"}, "sources")
    need(type(evidence["schema_version"]) is int and evidence["schema_version"] == 1, "Unsupported source schema version")
    need(isinstance(evidence["sources"], list) and bool(evidence["sources"]), "sources: expected non-empty sources")
    source_paths = []
    for source in evidence["sources"]:
        keys(source, {"id", "path", "sha256", "format", "blocks"}, "source")
        text(source["path"], "source.path")
        # Resolve only explicit source entries created by extract, never paths found inside documents.
        original = (path.parent / source["path"]).resolve()
        need(original.is_file(), f"Original source is missing: {source['path']}")
        need(digest(original.read_bytes()) == source["sha256"], f"Source changed: {source['path']}; extract again and review the design")
        source_paths.append(original)
    fresh = extract_sources(source_paths, path.parent)
    need(fresh == evidence, "Evidence differs from the original extraction; regenerate sources.json instead of editing it")
    return evidence


def validate_plan(plan, evidence):
    need(isinstance(plan, dict), "plan: expected an object")
    version = plan.get("schema_version")
    need(type(version) is int and version in {1, 2}, "Unsupported plan schema version")
    required = {"schema_version", "title", "mode", "source_fingerprints", "overview", "requirements", "test_points", "questions", "limitations"}
    note_fields = {"strategy", "preparation", "completion"}
    if version == 2:
        required |= {"scope", "modules"}
    keys(plan, required, "plan", note_fields)
    for name in ("title", "overview"):
        text(plan[name], name)
    enum(plan["mode"], {"outline", "plan"}, "mode")
    need(plan["source_fingerprints"] == {s["id"]: s["sha256"] for s in evidence["sources"]}, "source_fingerprints must match every source ID and SHA-256")
    strings(plan["limitations"], "limitations")
    blocks = {b["id"]: b for s in evidence["sources"] for b in s["blocks"]}
    reqs = indexed(plan["requirements"], "REQ", "requirements")
    points = indexed(plan["test_points"], "TP", "test_points")
    questions = indexed(plan["questions"], "Q", "questions")
    need(bool(reqs), "requirements cannot be empty")
    for identity, requirement in reqs.items():
        keys(requirement, {"id", "summary", "status", "evidence"}, identity)
        text(requirement["summary"], identity + ".summary")
        enum(requirement["status"], {"clear", "partial", "conflict"}, identity + ".status")
        references(requirement["evidence"], blocks, identity + ".evidence")
    for identity, question in questions.items():
        keys(question, {"id", "question", "reason", "requirement_ids", "evidence"}, identity)
        for name in ("question", "reason"):
            text(question[name], identity + "." + name)
        references(question["requirement_ids"], reqs, identity + ".requirement_ids")
        references(question["evidence"], blocks, identity + ".evidence")
        linked = {b for r in question["requirement_ids"] for b in reqs[r]["evidence"]}
        need(bool(set(question["evidence"]) & linked), f"{identity}: evidence must include a linked requirement's context")
    for identity, requirement in reqs.items():
        if requirement["status"] in {"partial", "conflict"}:
            need(any(identity in q["requirement_ids"] for q in questions.values()), f"{identity}: incomplete or conflicting requirement needs a question")
    modules = {}
    if version == 2:
        modules = indexed(plan["modules"], "MOD", "modules")
        scope = indexed(plan["scope"], "SCP", "scope")
        need(bool(modules) and bool(scope), "scope and modules cannot be empty")
        for identity, module in modules.items():
            keys(module, {"id", "name", "objects", "functions", "requirement_ids", "evidence"}, identity)
            text(module["name"], identity + ".name")
            strings(module["objects"], identity + ".objects", True)
            strings(module["functions"], identity + ".functions", True)
            references(module["requirement_ids"], reqs, identity + ".requirement_ids")
            references(module["evidence"], blocks, identity + ".evidence")
            linked = {b for r in module["requirement_ids"] for b in reqs[r]["evidence"]}
            need(bool(set(module["evidence"]) & linked), f"{identity}: evidence must include a linked requirement's context")
        active_modules = set()
        for identity, item in scope.items():
            keys(item, {"id", "name", "coverage", "boundary", "module_ids", "basis", "evidence", "question_ids"}, identity)
            for name in ("name", "boundary"):
                text(item[name], identity + "." + name)
            enum(item["coverage"], SCOPE, identity + ".coverage")
            enum(item["basis"], BASIS, identity + ".basis")
            references(item["module_ids"], modules, identity + ".module_ids", item["coverage"] == "included")
            references(item["evidence"], blocks, identity + ".evidence", item["basis"] != "suggested")
            references(item["question_ids"], questions, identity + ".question_ids", item["coverage"] == "pending")
            if item["coverage"] == "excluded":
                need(not item["module_ids"], f"{identity}: excluded scope cannot contain test modules")
            else:
                active_modules.update(item["module_ids"])
        need(active_modules == set(modules), "Every module must belong to included or pending scope")
    for identity, point in points.items():
        fields = {"id", "title", "requirement_ids", "evidence", "basis", "method", "preconditions", "action", "expected", "status", "question_ids", "priority", "priority_reason"}
        fields |= {"area"} if version == 1 else {"module_id", "function", "scenario_type"}
        keys(point, fields, identity)
        for name in ("title", "method", "action"):
            text(point[name], identity + "." + name)
        if version == 1:
            text(point["area"], identity + ".area")
        else:
            text(point["module_id"], identity + ".module_id")
            need(point["module_id"] in modules, f"{identity}: unknown module {point['module_id']}")
            module = modules[point["module_id"]]
            text(point["function"], identity + ".function")
            need(point["function"] in module["functions"], f"{identity}: function is not declared by its module")
            enum(point["scenario_type"], SCENARIOS, identity + ".scenario_type")
        strings(point["preconditions"], identity + ".preconditions")
        references(point["requirement_ids"], reqs, identity + ".requirement_ids")
        if version == 2:
            need(set(point["requirement_ids"]) <= set(module["requirement_ids"]), f"{identity}: requirements do not belong to its module")
        references(point["evidence"], blocks, identity + ".evidence")
        references(point["question_ids"], questions, identity + ".question_ids", False)
        enum(point["basis"], BASIS, identity + ".basis")
        enum(point["status"], {"ready", "needs-confirmation"}, identity + ".status")
        enum(point["priority"], {"P0", "P1", "P2", "unassigned"}, identity + ".priority")
        need(isinstance(point["priority_reason"], str), f"{identity}.priority_reason must be text")
        if point["priority"] != "unassigned":
            text(point["priority_reason"], identity + ".priority_reason")
        linked = {b for r in point["requirement_ids"] for b in reqs[r]["evidence"]}
        need(bool(set(point["evidence"]) & linked), f"{identity}: evidence must include a linked requirement's context")
        if point["status"] == "ready":
            text(point["expected"], identity + ".expected")
            need(not point["question_ids"], f"{identity}: ready points cannot have unresolved question references")
            need(point["basis"] != "suggested", f"{identity}: suggested points require confirmation")
            need(not any(reqs[r]["status"] == "conflict" for r in point["requirement_ids"]), f"{identity}: conflicting requirement cannot have a ready point")
        else:
            need(point["expected"] is None, f"{identity}: unknown expected result must be null")
            need(bool(point["question_ids"]), f"{identity}: unresolved point needs a question")
            for q in point["question_ids"]:
                need(bool(set(point["requirement_ids"]) & set(questions[q]["requirement_ids"])), f"{identity}: {q} is unrelated to the linked requirements")
    if version == 2:
        for identity, module in modules.items():
            covered = {p["function"] for p in points.values() if p["module_id"] == identity}
            need(covered == set(module["functions"]), f"{identity}: every function needs a test point")
    for name in sorted(note_fields):
        if version == 1 and plan["mode"] == "plan":
            need(name in plan and isinstance(plan[name], list) and bool(plan[name]), f"plan mode requires non-empty {name}")
        if name not in plan:
            continue
        need(isinstance(plan[name], list), f"{name}: expected a list")
        for i, note in enumerate(plan[name], 1):
            context = f"{name}[{i}]"
            keys(note, {"text", "basis", "evidence", "question_ids"}, context)
            text(note["text"], context + ".text")
            enum(note["basis"], BASIS, context + ".basis")
            references(note["evidence"], blocks, context + ".evidence", note["basis"] != "suggested")
            references(note["question_ids"], questions, context + ".question_ids", False)
    return {"requirements": len(reqs), "test_points": len(points), "questions": len(questions)}


def coverage_rows(plan):
    rows = []
    for req in plan["requirements"]:
        points = [p for p in plan["test_points"] if req["id"] in p["requirement_ids"]]
        questions = [q["id"] for q in plan["questions"] if req["id"] in q["requirement_ids"]]
        ready = any(p["status"] == "ready" for p in points)
        pending = bool(questions) or req["status"] != "clear" or any(p["status"] != "ready" for p in points)
        if ready:
            state = "部分待确认" if pending else "已设计"
        else:
            state = "待确认" if pending else "未设计"
        rows.append((req["id"], ", ".join(p["id"] for p in points) or "—", state, ", ".join(questions) or "—"))
    return rows


def safe(value):
    # Keep code and normal Markdown readable while preventing raw HTML execution.
    return html.escape(str(value), quote=False)


def cell(value):
    return safe(value).replace("|", "\\|").replace("\n", "<br>")


def markdown_table(headers, rows):
    lines = ["| " + " | ".join(cell(h) for h in headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(cell(c) for c in row) + " |" for row in rows)
    return lines + [""]


def compact_modules(plan):
    """Keep v1 designs readable without guessing their scenario classifications."""
    if plan["schema_version"] == 2:
        return plan["modules"]
    modules = []
    for area in dict.fromkeys(p["area"] for p in plan["test_points"]):
        points = [p for p in plan["test_points"] if p["area"] == area]
        modules.append({
            "id": area, "name": area, "objects": [area],
            "functions": list(dict.fromkeys(p["title"] for p in points)),
            "requirement_ids": list(dict.fromkeys(r for p in points for r in p["requirement_ids"])),
        })
    return modules


def provenance_comment(plan, evidence, source_paths):
    """Preserve audit data without adding sections to the reading view."""
    payload = {
        "plan": plan,
        "sources": [{
            "id": source["id"], "path": source_paths[source["id"]], "sha256": source["sha256"],
            "blocks": [{key: block[key] for key in ("id", "locator", "heading")} for block in source["blocks"]],
        } for source in evidence["sources"]],
        "warnings": evidence["warnings"],
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Prevent text from closing the comment or becoming executable HTML.
    raw = raw.replace("--", r"\u002d\u002d").replace("<", r"\u003c").replace(">", r"\u003e")
    return "<!-- spec2testplan-provenance\n" + raw + "\n-->"


def render_plan(plan, evidence, evidence_dir=None, document_dir=None):
    stats = validate_plan(plan, evidence)
    source_paths = {source["id"]: source["path"] for source in evidence["sources"]}
    if evidence_dir is not None and document_dir is not None:
        source_paths = {
            source["id"]: os.path.relpath((Path(evidence_dir) / source["path"]).resolve(), Path(document_dir).resolve())
            for source in evidence["sources"]
        }
    modules = compact_modules(plan)
    questions = {q["id"]: q for q in plan["questions"]}
    lines = [f"# {safe(plan['title'])}", "", "> 设计草稿 · 未执行测试", "",
             "## 需求简述", "", safe(plan["overview"]), "",
             f"{len(modules)} 个模块，{stats['test_points']} 个测试点。", ""]
    # Source paths remain readable and relative to the delivered document.
    lines.append("来源：" + "；".join(safe(source_paths[s["id"]]) for s in evidence["sources"]) + "。")
    lines += ["", "## 测试范围", ""]
    if plan["schema_version"] == 2:
        rows = [(item["name"], SCOPE[item["coverage"]], item["boundary"]) for item in plan["scope"]]
    else:
        rows = [(module["name"], "纳入", "；".join(module["functions"])) for module in modules]
    lines += markdown_table(["范围项", "是否测试", "范围边界"], rows)
    # Only material limitations belong in the reading view, not process boilerplate.
    if plan["schema_version"] == 2:
        lines.extend("- " + safe(item) for item in plan["limitations"])
        if plan["limitations"]:
            lines.append("")
    if evidence["warnings"]:
        lines += ["材料提示：存在提取或视觉内容限制，相关范围需核对原文。", ""]
    lines += ["## 测试模块与对象", ""]
    lines += markdown_table(["模块", "测试对象", "主要功能"], [
        (m["name"], "、".join(m["objects"]), "；".join(m["functions"])) for m in modules])
    lines += ["## 测试点与方法", ""]
    if not modules:
        lines += ["材料不足以确定测试模块，需补充业务规则。", ""]
    emitted_questions = set()
    for module in modules:
        lines += [f"### {safe(module['name'])}", ""]
        points = [p for p in plan["test_points"] if p.get("module_id", p.get("area")) == module["id"]]
        rows = []
        for point in points:
            check = point["title"] + "：" + point["action"]
            if point["preconditions"]:
                check = "条件：" + "；".join(point["preconditions"]) + "。" + check
            expected = point["expected"]
            if expected is None:
                expected = "待确认：" + "；".join(questions[q]["question"] for q in point["question_ids"])
                emitted_questions.update(point["question_ids"])
            function = point.get("function", module["name"])
            scenario = SCENARIOS.get(point.get("scenario_type"), "未分类")
            rows.append((function, scenario, point["id"] + " " + check, expected, point["method"]))
        lines += markdown_table(["功能", "场景", "测试点", "关键预期", "测试方法"], rows)
        module_questions = [q for q in plan["questions"]
                            if set(q["requirement_ids"]) & set(module["requirement_ids"])
                            and q["id"] not in emitted_questions]
        for question in module_questions:
            lines.append("- 需确认：" + safe(question["question"]))
            emitted_questions.add(question["id"])
        if module_questions:
            lines.append("")
    # A legacy design may have unresolved requirements outside any area.
    for question in plan["questions"]:
        if question["id"] not in emitted_questions:
            lines.append("- 需确认：" + safe(question["question"]))
    lines += ["", COMPACT_STYLE, "", provenance_comment(plan, evidence, source_paths)]
    return "\n".join(lines).rstrip() + "\n"
