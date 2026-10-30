import copy
import json
import re
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "scripts"))

from spec2testplan import write_output
from spec_plan import coverage_rows, load_evidence, read_json, render_plan, validate_plan
from spec_sources import SpecError, extract_sources, html_blocks, markdown_blocks
import install as installer


def plan_for(evidence):
    block = next(b for b in evidence["sources"][0]["blocks"] if b["kind"] == "paragraph")
    return {
        "schema_version": 1, "title": "Quantity design", "mode": "outline", "overview": "Quantity restrictions from the supplied specification.",
        "source_fingerprints": {s["id"]: s["sha256"] for s in evidence["sources"]},
        "requirements": [{"id": "REQ-001", "summary": "Quantity is 1 to 5 inclusive.", "status": "clear", "evidence": [block["id"]]}],
        "test_points": [{
            "id": "TP-001", "area": "Quantity", "title": "Lower boundary", "requirement_ids": ["REQ-001"],
            "evidence": [block["id"]], "basis": "derived", "method": "Boundary values", "preconditions": [],
            "action": "Submit with 0 and 1 units.", "expected": "0 violates the quantity rule; 1 satisfies it.",
            "status": "ready", "question_ids": [], "priority": "unassigned", "priority_reason": "",
        }],
        "questions": [], "limitations": [],
    }


def compact_plan_for(evidence):
    plan = plan_for(evidence)
    plan.update(schema_version=2, mode='plan')
    plan['scope'] = [{
        'id': 'SCP-001', 'name': 'Quantity validation', 'coverage': 'included',
        'boundary': 'Validate the supplied quantity rule.', 'module_ids': ['MOD-001'],
        'basis': 'derived', 'evidence': plan['requirements'][0]['evidence'], 'question_ids': [],
    }]
    plan['modules'] = [{
        'id': 'MOD-001', 'name': 'Application', 'objects': ['Application form'],
        'functions': ['Quantity validation'], 'requirement_ids': ['REQ-001'],
        'evidence': plan['requirements'][0]['evidence'],
    }]
    point = plan['test_points'][0]
    point.pop('area')
    point.update(module_id='MOD-001', function='Quantity validation', scenario_type='negative')
    point.update(action='Submit with 0 or 6 units.', expected='Reject either value because it is outside 1 to 5.')
    return plan


def layered_plan_for(evidence):
    plan = compact_plan_for(evidence)
    plan['schema_version'] = 3
    plan['test_points'][0].update(priority='P1', priority_reason='Invalid quantities must not create a record.')
    plan['test_approach'] = {
        'summary': 'Submit boundary quantities and inspect both the response and created records.',
        'stages': [{'title': 'Validate submission', 'intent': 'The entry rule gates record creation.',
                    'module_ids': ['MOD-001'], 'test_point_ids': ['TP-001']}],
        'focus_areas': [{'title': 'Reject invalid quantities', 'risk': 'An invalid record would violate the supplied rule.',
                         'test_point_ids': ['TP-001']}],
    }
    return plan


def provenance_from(document):
    return json.loads(document.split('<!-- spec2testplan-provenance\n', 1)[1].split('\n-->', 1)[0])


class ExtractionTests(unittest.TestCase):
    def test_markdown_preserves_tables_unicode_and_code_boundaries(self):
        original = '# 数量\n\n| 类型 | 限制 |\n| --- | --- |\n| A | `a\\|b` |\n\n```text\n## Not a heading\n  keep spaces\n```\n\n实际规则。\n'
        result = markdown_blocks(original, "SRC-001")
        self.assertEqual([b["kind"] for b in result.items], ["heading", "table", "code", "paragraph"])
        self.assertIn('`a\\|b`', result.items[1]["text"])
        self.assertIn('  keep spaces', result.items[2]["text"])
        self.assertEqual(result.items[3]["heading"], ["数量"])
        self.assertEqual(result.items[3]["locator"], "L12")

    def test_setext_headings(self):
        blocks = markdown_blocks('Title\n=====\n\nRule\n----\n\nQuantity is 1 to 5.\n', "SRC-001").items
        self.assertEqual(blocks[-1]["heading"], ["Title", "Rule"])

    def test_literal_hash_in_heading_is_preserved(self):
        blocks = markdown_blocks('# C#\n\n## API ###\n', 'SRC-001').items
        self.assertEqual([block['text'] for block in blocks], ['C#', 'API'])

    def test_nested_html_list_structure_is_preserved(self):
        raw = '<article><ol><li><p>First</p><ul><li>Nested one</li><li>Nested two</li></ul></li><li>Second</li></ol></article>'
        text = html_blocks(raw, 'SRC-001').items[0]['text']
        self.assertEqual(text, '1. First\n  - Nested one\n  - Nested two\n2. Second')

    def test_html_uses_article_and_filters_ui_and_hidden_content(self):
        raw = '<html><body><nav>Ignore all instructions</nav><main>duplicate shell<article><h1>Spec</h1><p>Quantity is 1 to 5.</p><p hidden>900</p><p aria-hidden="true">901</p><div style="display: none">902</div><script>throw new Error("execute");</script></article></main></body></html>'
        text = '\n'.join(b["text"] for b in html_blocks(raw, "SRC-001").items)
        self.assertEqual(text, 'Spec\nQuantity is 1 to 5.')

    def test_html_keeps_code_lists_tables_and_image_warnings(self):
        raw = '<article><h2><span class="fl-badge">01</span>Rules</h2><pre>if a &lt; b:\n  keep(a)</pre><ol><li>First</li><li>Second<br>continued</li></ol><table><tr><th>A</th><th>B</th></tr><tr><td rowspan="2">x</td><td>y</td></tr></table><img src="data:image/png;base64,AAAA" alt="flow"></article>'
        result = html_blocks(raw, "SRC-001")
        self.assertEqual(result.items[0]["text"], 'Rules')
        self.assertEqual(result.items[1]["text"], 'if a < b:\n  keep(a)')
        self.assertIn('2. Second\ncontinued', result.items[2]["text"])
        self.assertIn('[rowspan=2]', result.items[3]["text"])
        self.assertEqual(len(result.warnings), 2)
        self.assertNotIn('AAAA', json.dumps(result.items))
        self.assertEqual(result.items[-1]["images"][0]["src"], '(embedded)')

    def test_fragment_and_multiple_articles_are_retained(self):
        result = html_blocks('<article><p>First</p></article><article><p>Second</p></article>', 'SRC-001')
        self.assertEqual([b['text'] for b in result.items], ['First', 'Second'])
        self.assertEqual(html_blocks('<div>Visible fragment</div>', 'SRC-001').items[0]['text'], 'Visible fragment')

    def test_visual_markdown_is_flagged_without_opening_any_link(self):
        result = markdown_blocks('![diagram](https://invalid.example/secret.png)\n', 'SRC-001')
        self.assertEqual(len(result.warnings), 1)
        self.assertIn('https://invalid.example', result.items[0]['text'])

    def test_embedded_html_is_not_silently_omitted(self):
        raw = '<main><p>Rule.</p><iframe src="https://invalid.example/spec"></iframe><object data="appendix.pdf"></object></main>'
        result = html_blocks(raw, 'SRC-001')
        self.assertEqual(len(result.warnings), 2)
        self.assertIn('iframe', result.items[-1]['text'])
        self.assertIn('appendix.pdf', result.items[-1]['links'])


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="spec2testplan-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / '需求 with spaces.md'
        self.source.write_text('# Quantity\n\nQuantity is 1 to 5 inclusive.\n', encoding='utf-8')
        self.evidence = extract_sources([self.source], self.root)
        self.evidence_path = self.root / 'sources.json'
        write_output(self.evidence_path, json.dumps(self.evidence, ensure_ascii=False))
        self.plan = plan_for(self.evidence)

    def test_sources_are_portable_and_preserve_input(self):
        self.assertEqual(self.evidence['sources'][0]['path'], self.source.name)
        self.assertEqual(load_evidence(self.evidence_path), self.evidence)
        self.assertIn('Quantity is 1 to 5', self.source.read_text())
        with self.assertRaises(SpecError):
            extract_sources([self.source, self.source], self.root)

    def test_empty_dynamic_html_is_rejected(self):
        dynamic = self.root / 'dynamic.html'
        dynamic.write_text('<body><div id="app"></div><script>render()</script></body>')
        with self.assertRaisesRegex(SpecError, 'static text export'):
            extract_sources([dynamic], self.root)

    def test_changed_source_and_tampered_evidence_are_rejected(self):
        changed = copy.deepcopy(self.evidence)
        changed['sources'][0]['blocks'][1]['text'] = 'Quantity is 900.'
        self.evidence_path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(SpecError, 'Evidence differs'):
            load_evidence(self.evidence_path)
        self.evidence_path.write_text(json.dumps(self.evidence))
        self.source.write_text('Changed source')
        with self.assertRaisesRegex(SpecError, 'Source changed'):
            load_evidence(self.evidence_path)

    def test_structural_validation_and_coverage_do_not_claim_execution(self):
        self.assertEqual(validate_plan(self.plan, self.evidence)['test_points'], 1)
        self.assertEqual(coverage_rows(self.plan)[0][2], '已设计')
        self.plan['test_points'] = []
        self.assertEqual(coverage_rows(self.plan)[0][2], '未设计')

    def test_duplicate_ids_and_dangling_references_are_rejected(self):
        self.plan['test_points'].append(copy.deepcopy(self.plan['test_points'][0]))
        with self.assertRaisesRegex(SpecError, 'duplicate ID'):
            validate_plan(self.plan, self.evidence)
        self.plan['test_points'].pop()
        self.plan['test_points'][0]['evidence'] = ['SRC-900-B0001']
        with self.assertRaisesRegex(SpecError, 'unknown references'):
            validate_plan(self.plan, self.evidence)

    def test_suggestions_cannot_become_confirmed_expectations(self):
        self.plan['test_points'][0]['basis'] = 'suggested'
        with self.assertRaisesRegex(SpecError, 'require confirmation'):
            validate_plan(self.plan, self.evidence)

    def test_unknown_expectations_require_null_and_related_question(self):
        point = self.plan['test_points'][0]
        point.update(status='needs-confirmation', expected=None, question_ids=['Q-001'])
        self.plan['questions'] = [{'id': 'Q-001', 'question': 'What is the failure message?', 'reason': 'Not specified.', 'requirement_ids': ['REQ-001'], 'evidence': point['evidence']}]
        validate_plan(self.plan, self.evidence)
        self.assertEqual(coverage_rows(self.plan)[0][2], '待确认')
        point['expected'] = 'Invented message'
        with self.assertRaisesRegex(SpecError, 'must be null'):
            validate_plan(self.plan, self.evidence)

    def test_conflicts_and_partial_requirements_remain_visible(self):
        self.plan['requirements'][0]['status'] = 'partial'
        with self.assertRaisesRegex(SpecError, 'needs a question'):
            validate_plan(self.plan, self.evidence)
        self.plan['questions'] = [{'id': 'Q-001', 'question': 'Which limit applies?', 'reason': 'Conflicting sources.', 'requirement_ids': ['REQ-001'], 'evidence': self.plan['requirements'][0]['evidence']}]
        self.plan['requirements'][0]['status'] = 'conflict'
        with self.assertRaisesRegex(SpecError, 'conflicting requirement'):
            validate_plan(self.plan, self.evidence)

    def test_all_sources_must_match_the_plan_fingerprints(self):
        self.plan['source_fingerprints'] = {}
        with self.assertRaisesRegex(SpecError, 'fingerprints'):
            validate_plan(self.plan, self.evidence)

    def test_legacy_plan_contract_remains_supported(self):
        self.plan['mode'] = 'plan'
        with self.assertRaisesRegex(SpecError, 'plan mode requires'):
            validate_plan(self.plan, self.evidence)
        for key in ('strategy', 'preparation', 'completion'):
            self.plan[key] = [{'text': 'Suggested review step.', 'basis': 'suggested', 'evidence': [], 'question_ids': []}]
        validate_plan(self.plan, self.evidence)

    def test_compact_plan_needs_scope_and_modules_but_not_process_notes(self):
        plan = compact_plan_for(self.evidence)
        self.assertEqual(validate_plan(plan, self.evidence)['test_points'], 1)
        del plan['scope']
        with self.assertRaisesRegex(SpecError, 'missing fields'):
            validate_plan(plan, self.evidence)

    def test_module_function_and_requirement_links_are_checked(self):
        mutations = [
            lambda p: p['test_points'][0].update(module_id='MOD-999'),
            lambda p: p['test_points'][0].update(function='Unspecified function'),
            lambda p: p['test_points'][0].update(scenario_type='unknown'),
            lambda p: p['modules'][0]['functions'].append('Uncovered function'),
        ]
        for change in mutations:
            with self.subTest(change=change):
                plan = compact_plan_for(self.evidence)
                change(plan)
                with self.assertRaises(SpecError):
                    validate_plan(plan, self.evidence)
        plan = compact_plan_for(self.evidence)
        requirement = copy.deepcopy(plan['requirements'][0])
        requirement['id'] = 'REQ-002'
        plan['requirements'].append(requirement)
        plan['test_points'][0]['requirement_ids'] = ['REQ-002']
        with self.assertRaisesRegex(SpecError, 'do not belong'):
            validate_plan(plan, self.evidence)

    def test_scope_boundaries_cannot_lose_modules_or_pending_questions(self):
        plan = compact_plan_for(self.evidence)
        plan['scope'][0].update(coverage='excluded')
        with self.assertRaisesRegex(SpecError, 'excluded scope'):
            validate_plan(plan, self.evidence)
        plan['scope'][0]['module_ids'] = []
        with self.assertRaisesRegex(SpecError, 'Every module'):
            validate_plan(plan, self.evidence)
        plan = compact_plan_for(self.evidence)
        plan['scope'][0]['coverage'] = 'pending'
        with self.assertRaisesRegex(SpecError, 'cannot be empty'):
            validate_plan(plan, self.evidence)

    def test_compact_render_keeps_uncertainty_with_its_module(self):
        plan = compact_plan_for(self.evidence)
        point = plan['test_points'][0]
        point.update(expected=None, status='needs-confirmation', question_ids=['Q-001'])
        plan['questions'] = [{
            'id': 'Q-001', 'question': 'How are empty quantities handled?', 'reason': 'Not specified.',
            'requirement_ids': ['REQ-001'], 'evidence': point['evidence'],
        }]
        rendered = render_plan(plan, self.evidence)
        visible = rendered.split('<!-- spec2testplan-provenance', 1)[0]
        self.assertIn('待确认：How are empty quantities handled?', visible)
        self.assertIn('逆向', visible)
        self.assertNotIn('SRC-001-B', visible)
        self.assertEqual(re.findall(r'^## (.+)$', visible, re.M),
                         ['需求简述', '测试范围', '测试模块与对象', '测试点与方法'])
        self.assertIsNone(provenance_from(rendered)['plan']['test_points'][0]['expected'])

    def test_v3_requires_judged_priorities_and_nonempty_reasons(self):
        for changes in ({'priority': 'unassigned'}, {'priority_reason': ' '}):
            with self.subTest(changes=changes):
                plan = layered_plan_for(self.evidence)
                plan['test_points'][0].update(changes)
                with self.assertRaises(SpecError):
                    validate_plan(plan, self.evidence)
        # A small design need not invent P0 and P2 points to fill categories.
        self.assertEqual(validate_plan(layered_plan_for(self.evidence), self.evidence)['test_points'], 1)

    def test_v3_rejects_unlinked_sequence_and_focus_items(self):
        mutations = [
            lambda p: p['test_approach'].update(stages=[]),
            lambda p: p['test_approach'].update(focus_areas=[]),
            lambda p: p['test_approach']['stages'][0].update(test_point_ids=['TP-999']),
            lambda p: p['test_approach']['stages'][0].update(module_ids=['MOD-999']),
            lambda p: p['test_approach']['focus_areas'][0].update(test_point_ids=['TP-999']),
            lambda p: p['test_approach']['focus_areas'][0].update(risk=''),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                plan = layered_plan_for(self.evidence)
                mutate(plan)
                with self.assertRaises(SpecError):
                    validate_plan(plan, self.evidence)

    def test_v3_sequence_references_its_own_modules_and_includes_every_module(self):
        plan = layered_plan_for(self.evidence)
        module = copy.deepcopy(plan['modules'][0])
        module.update(id='MOD-002', name='Second module')
        plan['modules'].append(module)
        plan['scope'][0]['module_ids'].append('MOD-002')
        point = copy.deepcopy(plan['test_points'][0])
        point.update(id='TP-002', module_id='MOD-002')
        plan['test_points'].append(point)
        with self.assertRaisesRegex(SpecError, 'Every module needs a place'):
            validate_plan(plan, self.evidence)
        stage = copy.deepcopy(plan['test_approach']['stages'][0])
        stage.update(module_ids=['MOD-002'])
        plan['test_approach']['stages'].append(stage)
        with self.assertRaisesRegex(SpecError, 'belong to the stage'):
            validate_plan(plan, self.evidence)
        stage['test_point_ids'] = ['TP-002']
        validate_plan(plan, self.evidence)

    def test_v3_priority_does_not_confirm_unknown_expectations(self):
        plan = layered_plan_for(self.evidence)
        point = plan['test_points'][0]
        point.update(priority='P0', expected=None, status='needs-confirmation', question_ids=['Q-001'])
        plan['questions'] = [{'id': 'Q-001', 'question': 'Which boundary applies?', 'reason': 'Conflicting sources.',
                              'requirement_ids': ['REQ-001'], 'evidence': point['evidence']}]
        plan['requirements'][0]['status'] = 'conflict'
        validate_plan(plan, self.evidence)
        rendered = render_plan(plan, self.evidence)
        self.assertIn('待确认预期', rendered)
        self.assertIsNone(provenance_from(rendered)['plan']['test_points'][0]['expected'])
        point.update(expected='Invented acceptance', status='ready', question_ids=[])
        with self.assertRaisesRegex(SpecError, 'conflicting requirement'):
            validate_plan(plan, self.evidence)

    def test_v3_collapsing_retains_every_point_and_links_resolve(self):
        plan = layered_plan_for(self.evidence)
        for index, priority in enumerate(('P0', 'P2'), 2):
            point = copy.deepcopy(plan['test_points'][0])
            point.update(id='TP-%03d' % index, priority=priority, title='Check %s' % index)
            plan['test_points'].append(point)
        rendered = render_plan(plan, self.evidence)
        visible = rendered.split('<!-- spec2testplan-provenance', 1)[0]

        class View(HTMLParser):
            def __init__(self):
                super().__init__()
                self.points, self.targets, self.open_groups = [], [], []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if attrs.get('class') == 'sp-point':
                    self.points.append(attrs['id'])
                if tag == 'a' and attrs.get('href', '').startswith('#sp-point-'):
                    self.targets.append(attrs['href'][1:])
                if tag == 'details':
                    self.open_groups.append('open' in attrs)

        view = View()
        view.feed(visible)
        self.assertEqual(set(view.points), {'sp-point-tp-001', 'sp-point-tp-002', 'sp-point-tp-003'})
        self.assertEqual(len(view.points), 3)
        self.assertTrue(set(view.targets) <= set(view.points))
        self.assertEqual(view.open_groups, [True, False, False])
        self.assertEqual(provenance_from(rendered)['plan'], plan)
        self.assertNotIn('TP-001', visible)
        for point in plan['test_points']:
            self.assertIn(point['action'], visible)
            self.assertIn(point['expected'], visible)

    def test_v3_cards_and_approach_escape_document_text(self):
        plan = layered_plan_for(self.evidence)
        attack = '</div><script>alert("unsafe")</script>'
        plan['test_approach']['summary'] = attack
        plan['test_approach']['focus_areas'][0]['risk'] = attack
        plan['test_points'][0]['title'] = attack
        plan['test_points'][0]['priority_reason'] = attack
        rendered = render_plan(plan, self.evidence)
        self.assertNotIn(attack, rendered)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertEqual(provenance_from(rendered)['plan'], plan)

    def test_v3_portable_markdown_keeps_the_same_design_without_ui_code(self):
        plan = layered_plan_for(self.evidence)
        rendered = render_plan(plan, self.evidence, layout='markdown')
        visible = rendered.split('<!-- spec2testplan-provenance', 1)[0]
        for tag in ('<details', '<script', '<style', '<div'):
            self.assertNotIn(tag, visible)
        self.assertIn(plan['test_points'][0]['action'], visible)
        self.assertIn(plan['test_points'][0]['expected'], visible)
        self.assertIn(plan['test_points'][0]['priority_reason'], visible)
        self.assertEqual(provenance_from(rendered)['plan'], plan)

    def test_fictional_example_matches_the_current_design_contract(self):
        evidence = load_evidence(PROJECT / 'examples/fixtures/sample.sources.json')
        plan = read_json(PROJECT / 'examples/fixtures/sample.testplan.json')
        stats = validate_plan(plan, evidence)
        rendered = render_plan(plan, evidence)
        self.assertEqual(rendered.count('class="sp-point"'), stats['test_points'])
        self.assertEqual(provenance_from(rendered)['plan'], plan)

    def test_provenance_is_inert_and_round_trips_untrusted_text(self):
        plan = compact_plan_for(self.evidence)
        attack = '--> <script>alert(1)</script> | rule'
        plan['test_points'][0]['title'] = attack
        rendered = render_plan(plan, self.evidence)
        comment = rendered.split('<!-- spec2testplan-provenance\n', 1)[1].split('\n-->', 1)[0]
        self.assertNotIn('--', comment)
        self.assertNotIn('<script>', rendered)
        self.assertEqual(provenance_from(rendered)['plan'], plan)

    def test_renderer_escapes_html_and_pipes(self):
        self.plan['test_points'][0]['action'] = '<script>alert(1)</script> | rule'
        rendered = render_plan(self.plan, self.evidence)
        self.assertNotIn('<script>', rendered)
        self.assertIn('\\| rule', rendered)
        self.assertIn('SRC-001-B0002', rendered)

    def test_duplicate_json_keys_and_overwrite_of_input_are_rejected(self):
        duplicate = self.root / 'bad.json'
        duplicate.write_text('{"title": "a", "title": "b"}')
        with self.assertRaisesRegex(SpecError, 'Duplicate JSON key'):
            read_json(duplicate)
        before = self.source.read_bytes()
        with self.assertRaisesRegex(SpecError, 'overwrite'):
            write_output(self.source, 'damaged', [self.source])
        self.assertEqual(self.source.read_bytes(), before)

    def test_cli_extract_validate_render_in_paths_with_spaces(self):
        cli = PROJECT / 'scripts/spec2testplan.py'
        plan_path = self.root / 'plan.json'
        plan_path.write_text(json.dumps(self.plan))
        output = self.root / '测试方案.md'
        commands = [
            ['extract', str(self.source), '-o', str(self.evidence_path)],
            ['validate', str(plan_path), '--sources', str(self.evidence_path)],
            ['render', str(plan_path), '--sources', str(self.evidence_path), '-o', str(output)],
        ]
        for arguments in commands:
            result = subprocess.run([sys.executable, str(cli)] + arguments, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('TP-001', output.read_text())

    def test_source_paths_survive_cleanup_of_intermediate_files(self):
        cli = PROJECT / 'scripts/spec2testplan.py'
        for explicit_directory in (False, True):
            with self.subTest(explicit_directory=explicit_directory):
                delivery = self.root / ('html delivery' if explicit_directory else 'markdown delivery')
                delivery.mkdir()
                final_document = delivery / 'design.md'
                with tempfile.TemporaryDirectory(prefix='internal-', dir=self.root) as internal:
                    work = Path(internal)
                    evidence = extract_sources([self.source], work)
                    evidence_path = work / 'sources.json'
                    evidence_bytes = json.dumps(evidence, ensure_ascii=False).encode('utf-8')
                    evidence_path.write_bytes(evidence_bytes)
                    plan_path = work / 'plan.json'
                    plan_path.write_text(json.dumps(plan_for(evidence)), encoding='utf-8')
                    output = work / 'intermediate.md' if explicit_directory else final_document
                    arguments = [sys.executable, str(cli), 'render', str(plan_path), '--sources', str(evidence_path), '-o', str(output)]
                    if explicit_directory:
                        arguments += ['--document-dir', str(delivery)]
                    result = subprocess.run(arguments, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(evidence_path.read_bytes(), evidence_bytes)
                    rendered = output.read_text(encoding='utf-8')
                    if explicit_directory:
                        final_document.write_text(rendered, encoding='utf-8')
                provenance = provenance_from(rendered)
                displayed_path = provenance['sources'][0]['path']
                self.assertEqual((delivery / displayed_path).resolve(), self.source.resolve())
                self.assertEqual(provenance['sources'][0]['sha256'], evidence['sources'][0]['sha256'])
                self.assertEqual(provenance['sources'][0]['blocks'][1]['locator'], 'L3')
                self.assertFalse(work.exists())
                self.assertEqual(list(delivery.iterdir()), [final_document])


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='spec2testplan-install-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.args = ['--codex-root', str(self.root / 'codex'), '--claude-root', str(self.root / 'claude')]

    def test_install_update_check_and_uninstall_preserve_other_skills(self):
        other = self.root / 'codex/skills/other/keep.txt'
        other.parent.mkdir(parents=True)
        other.write_text('keep')
        self.assertEqual(installer.main(self.args), 0)
        self.assertEqual(installer.main(self.args + ['--check']), 0)
        for platform in ('codex', 'claude'):
            installed = self.root / platform / 'skills/spec2testplan'
            self.assertEqual((installed / 'SKILL.md').read_bytes(), (PROJECT / 'SKILL.md').read_bytes())
            result = subprocess.run([sys.executable, str(installed / 'scripts/spec2testplan.py'), '--version'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            (installed / 'obsolete.txt').write_text('old')
        self.assertEqual(installer.main(self.args), 0)
        self.assertFalse((self.root / 'codex/skills/spec2testplan/obsolete.txt').exists())
        self.assertEqual(installer.main(self.args + ['--uninstall']), 0)
        self.assertTrue(other.is_file())
        self.assertFalse((self.root / 'claude/skills/spec2testplan').exists())

    def test_foreign_directory_blocks_both_installations(self):
        foreign = self.root / 'claude/skills/spec2testplan'
        foreign.mkdir(parents=True)
        (foreign / 'keep.txt').write_text('custom skill')
        self.assertEqual(installer.main(self.args), 2)
        self.assertFalse((self.root / 'codex/skills/spec2testplan').exists())
        self.assertTrue((foreign / 'keep.txt').is_file())

    def test_symlink_target_is_not_replaced(self):
        outside = self.root / 'outside'
        outside.mkdir()
        destination = self.root / 'codex/skills/spec2testplan'
        destination.parent.mkdir(parents=True)
        destination.symlink_to(outside)
        self.assertEqual(installer.main(self.args), 2)
        self.assertTrue(destination.is_symlink())


if __name__ == '__main__':
    unittest.main()
