"""Reading layers for a risk-oriented test design; no external assets."""

import html


PRIORITIES = {"P0": "关键结果", "P1": "分支与联动", "P2": "补充回归"}
SCENARIOS = {"positive": "正向", "negative": "逆向", "exception": "异常"}

READING_STYLE = """<style>
.hero-meta{display:none}
.wrap{max-width:1160px;padding:36px 40px 64px}
.content h2{margin-top:40px}.content h3{margin-top:30px}
.sp-stats{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0}
.sp-stat,.sp-badge{display:inline-block;border-radius:6px;padding:3px 8px;background:#eef2ff;color:#334155;font-size:12px;line-height:1.7}
.sp-p0{background:#fef2f2;color:#9f1239}.sp-p1{background:#eef2ff;color:#3730a3}.sp-p2{background:#f1f5f9;color:#475569}.sp-pending{background:#fffbeb;color:#92400e}
.sp-lead{border-left:3px solid #0f766e;padding:14px 20px;background:#f0fdfa;border-radius:0 12px 12px 0;line-height:1.9;margin:16px 0 24px}
.sp-route{display:grid;gap:12px;margin:16px 0 28px;counter-reset:route}
.sp-stage{display:grid;grid-template-columns:38px 1fr;gap:14px;border:1px solid #e2e8f0;border-radius:12px;padding:18px 20px;background:#fff;counter-increment:route}
.sp-stage::before{content:counter(route,decimal-leading-zero);font-size:18px;font-weight:700;color:#0f766e}
.sp-stage strong,.sp-focus strong{font-size:16px}.sp-stage p,.sp-focus p{margin:6px 0 10px}
.sp-links{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;line-height:1.8}.sp-links a{text-decoration:underline;text-underline-offset:3px}
.sp-objects{color:#64748b;font-size:12px;margin:5px 0 10px}
.sp-focus-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin:14px 0 24px}
.sp-focus{padding:18px 20px;border:1px solid #e2e8f0;border-top:3px solid #be123c;border-radius:10px;background:#fff}
.sp-focus p{font-size:13px;line-height:1.9;color:#475569}
.sp-help{font-size:12px;color:#64748b;line-height:1.9}
.sp-toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}
.sp-toolbar button{font:inherit;font-size:12px;border:1px solid #cbd5e1;border-radius:7px;padding:7px 12px;background:#fff;color:#334155;cursor:pointer}
.sp-module-meta{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin:8px 0 14px}
.sp-group{margin:12px 0;border:1px solid #e2e8f0;border-radius:10px;background:#fff;overflow:hidden}
.sp-group>summary{cursor:pointer;padding:13px 18px;background:#f8fafc;font-weight:600;font-size:13px;color:#334155}
.sp-group>summary span{font-weight:400;color:#64748b;margin-left:8px}
.sp-point{padding:18px 20px;border-top:1px solid #e2e8f0;scroll-margin-top:24px}
.sp-point:target{box-shadow:inset 4px 0 #0f766e;background:#f0fdfa}
.sp-point-title{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:9px}
.sp-point-title strong{font-size:14px}.sp-point-title small{color:#64748b;font-size:12px}
.sp-point-body{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px;font-size:13px;line-height:1.95;overflow-wrap:anywhere}
.sp-point-body p{margin:5px 0}.sp-label{font-size:11px;color:#64748b;font-weight:600;display:block}
.sp-expected{border-left:2px solid #cbd5e1;padding-left:14px}.sp-expected.sp-unconfirmed{border-color:#f59e0b;background:#fffbeb}
.sp-reason{font-size:12px;color:#64748b;margin-top:10px;line-height:1.8}.sp-method{font-size:11px;color:#64748b;margin-top:7px}
@media(max-width:760px){.wrap{padding:24px 18px}.sp-focus-grid,.sp-point-body{grid-template-columns:1fr}.sp-stage{padding:15px;gap:9px}.sp-point{padding:15px}.sp-expected{padding-left:10px}}
@media print{.sp-toolbar{display:none}.sp-point{break-inside:avoid}.sp-focus-grid{display:block}.sp-focus{margin-bottom:12px}.sp-group::details-content{content-visibility:visible!important;display:block!important}}
</style>"""

READING_SCRIPT = """<script>
(function(){
  function groups(){return Array.from(document.querySelectorAll('.sp-group'));}
  function reveal(){
    var id;try{id=decodeURIComponent(location.hash.slice(1));}catch(e){return;}
    var target=document.getElementById(id);
    if(!target||!target.classList.contains('sp-point'))return;
    var parent=target.closest('details');if(parent)parent.open=true;
    target.scrollIntoView({block:'start'});
  }
  document.addEventListener('click',function(event){
    var button=event.target.closest('[data-sp-view]');
    if(button)groups().forEach(function(group){group.open=button.dataset.spView==='all'||group.dataset.defaultOpen==='true';});
    var link=event.target.closest('a[href^="#sp-point-"]');
    if(link){var target=document.getElementById(link.hash.slice(1));if(target){var parent=target.closest('details');if(parent)parent.open=true;}}
  });
  window.addEventListener('hashchange',reveal);
  var previous=[];
  window.addEventListener('beforeprint',function(){previous=groups().map(function(group){var was=group.open;group.open=true;return was;});});
  window.addEventListener('afterprint',function(){groups().forEach(function(group,index){group.open=previous[index];});});
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',reveal);else reveal();
})();
</script>"""


def escape(value):
    return html.escape(str(value), quote=True).replace("\n", "<br>")


def point_anchor(point):
    return "sp-point-" + point["id"].lower()


def point_links(identities, points):
    links = []
    for identity in identities:
        point = points[identity]
        suffix = "（待确认）" if point["status"] != "ready" else ""
        links.append('<a href="#%s">%s%s</a>' % (
            point_anchor(point), escape(point["title"]), suffix))
    return '<div class="sp-links">' + "".join(links) + '</div>'


def render_stats(plan):
    pieces = ['<div class="sp-stats"><span class="sp-stat">%s 个模块 · %s 个测试点</span>' % (
        len(plan['modules']), len(plan['test_points']))]
    for priority in PRIORITIES:
        count = sum(p['priority'] == priority for p in plan['test_points'])
        if count:
            pieces.append('<span class="sp-badge sp-%s">%s · %s</span>' % (priority.lower(), priority, count))
    pending = sum(p['status'] != 'ready' for p in plan['test_points'])
    if pending:
        pieces.append('<span class="sp-badge sp-pending">其中待确认 · %s</span>' % pending)
    return ''.join(pieces) + '</div>'


def render_approach(plan, plain=False):
    approach = plan["test_approach"]
    modules = {m["id"]: m for m in plan["modules"]}
    points = {p["id"]: p for p in plan["test_points"]}
    if plain:
        lines = ['## 测试思路与重点', '', escape(approach['summary']), '', '**建议测试顺序**', '']
        for index, stage in enumerate(approach['stages'], 1):
            objects = '；'.join('、'.join(modules[m]['objects']) for m in stage['module_ids'])
            titles = '；'.join(points[p]['title'] + ('（待确认）' if points[p]['status'] != 'ready' else '')
                              for p in stage['test_point_ids'])
            lines += ['%s. **%s**：%s 对象：%s。重点检查：%s。' % (
                index, escape(stage['title']), escape(stage['intent']), escape(objects), escape(titles)), '']
        lines += ['**重点盯住的结果**', '']
        for focus in approach['focus_areas']:
            titles = '；'.join(points[p]['title'] for p in focus['test_point_ids'])
            lines += ['- **%s**：%s 关联检查：%s。' % (escape(focus['title']), escape(focus['risk']), escape(titles)), '']
        return lines + ['P0 关键结果；P1 分支与联动；P2 补充回归。顺序还需考虑前置依赖，待确认项先对齐预期。', '']
    lines = ['## 测试思路与重点', '', '<div class="sp-lead">%s</div>' % escape(approach["summary"]), '',
             '**建议测试顺序**', '', '<div class="sp-route">']
    for stage in approach["stages"]:
        names = " → ".join(modules[identity]["name"] for identity in stage["module_ids"])
        objects = "；".join("、".join(modules[identity]["objects"]) for identity in stage["module_ids"])
        lines.extend(['<div class="sp-stage"><div>', '<strong>%s</strong>' % escape(stage["title"]),
                      '<p>%s</p>' % escape(stage["intent"]),
                      '<div class="sp-objects">%s<br>对象：%s</div>' % (escape(names), escape(objects)),
                      point_links(stage["test_point_ids"], points), '</div></div>'])
    lines.extend(['</div>', '', '**重点盯住的结果**', '', '<div class="sp-focus-grid">'])
    for focus in approach["focus_areas"]:
        lines.extend(['<div class="sp-focus"><strong>%s</strong>' % escape(focus["title"]),
                      '<p>%s</p>' % escape(focus["risk"]), point_links(focus["test_point_ids"], points), '</div>'])
    lines.extend(['</div>', '', 'P0 关键结果；P1 分支与联动；P2 补充回归。优先级是依据改动与失败影响作出的测试判断，执行顺序还需考虑前置依赖。待确认项先对齐预期。', ''])
    return lines


def render_point(point, questions):
    priority = point["priority"]
    pending = point["status"] != "ready"
    expected = point["expected"] if not pending else "；".join(questions[q]["question"] for q in point["question_ids"])
    lines = ['<div class="sp-point" id="%s">' % point_anchor(point), '<div class="sp-point-title">',
             '<span class="sp-badge sp-%s">%s</span>' % (priority.lower(), priority),
             '<strong>%s</strong>' % escape(point["title"]),
             '<small>%s · %s</small>' % (escape(point["function"]), SCENARIOS[point["scenario_type"]]), '</div>',
             '<div class="sp-point-body"><div><span class="sp-label">验证什么</span>']
    if point["preconditions"]:
        lines.append('<p>条件：%s</p>' % escape("；".join(point["preconditions"])))
    lines.extend(['<p>%s</p></div>' % escape(point["action"]),
                  '<div class="sp-expected%s"><span class="sp-label">%s</span><p>%s</p></div></div>' % (
                      ' sp-unconfirmed' if pending else '', '待确认预期' if pending else '关键预期', escape(expected)),
                  '<div class="sp-reason">为何%s：%s</div>' % (priority, escape(point["priority_reason"])),
                  '<div class="sp-method">方法：%s</div></div>' % escape(point["method"])])
    return lines


def render_module(points, questions):
    pending = [p for p in points if p["status"] != "ready"]
    lines = ['<div class="sp-module-meta"><span class="sp-stat">%s 个测试点</span>' % len(points)]
    for priority in PRIORITIES:
        count = sum(p["priority"] == priority for p in points)
        if count:
            lines.append('<span class="sp-badge sp-%s">%s · %s</span>' % (priority.lower(), priority, count))
    if pending:
        lines.append('<span class="sp-badge sp-pending">待确认 · %s</span>' % len(pending))
    lines.append('</div>')
    groups = [(priority, [p for p in points if p["priority"] == priority and p["status"] == "ready"])
              for priority in PRIORITIES]
    groups.append(('pending', sorted(pending, key=lambda p: p['priority'])))
    for kind, items in groups:
        if not items:
            continue
        opened = kind in {'P0', 'pending'}
        label = '先确认预期' if kind == 'pending' else kind + ' · ' + PRIORITIES[kind]
        lines.append('<details class="sp-group" data-default-open="%s"%s><summary>%s<span>%s 个测试点</span></summary>' % (
            str(opened).lower(), ' open' if opened else '', label, len(items)))
        for point in items:
            lines.extend(render_point(point, questions))
        lines.append('</details>')
    lines.append('')
    return lines


def render_markdown_points(points, questions):
    lines = []
    for point in sorted(points, key=lambda p: p['priority']):
        pending = point['status'] != 'ready'
        expected = point['expected'] if not pending else '；'.join(questions[q]['question'] for q in point['question_ids'])
        lines += ['#### %s · %s%s' % (point['priority'], escape(point['title']), '（待确认）' if pending else ''), '',
                  '%s · %s · 方法：%s' % (escape(point['function']), SCENARIOS[point['scenario_type']], escape(point['method'])), '']
        if point['preconditions']:
            lines += ['条件：' + escape('；'.join(point['preconditions'])), '']
        lines += ['验证：' + escape(point['action']), '',
                  ('待确认预期：' if pending else '关键预期：') + escape(expected), '',
                  '优先级理由：' + escape(point['priority_reason']), '']
    return lines
