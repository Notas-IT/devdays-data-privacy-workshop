"""Guard learner/reference isolation and preserve student edits. No Docker required."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import layers


class LearnerRunnerTests(unittest.TestCase):
    def test_prepare_preserves_existing_student_work(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'layers' / layers.STAGES[0]
            source.mkdir(parents=True)
            (source / 'docker-compose.yml').write_text('name: devdays-agent-layer-00\nSTAGE_LEVEL: "0"\n')
            (source / 'security.sql').write_text('-- previous grants\n')
            with patch.object(layers, 'ROOT', root), contextlib.redirect_stdout(io.StringIO()):
                layers.prepare(1)
                target = root / '.practice' / layers.STAGES[1] / 'security.sql'
                target.write_text('-- student edits\n')
                with self.assertRaisesRegex(SystemExit, 'preserving your edits'):
                    layers.prepare(1)
                self.assertEqual(target.read_text(), '-- student edits\n')

    def test_practice_runs_cannot_select_reference_project_or_compose_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / '.practice' / layers.STAGES[1] / 'docker-compose.yml'
            config.parent.mkdir(parents=True)
            config.write_text('')
            completed = subprocess.CompletedProcess([], 0, '', '')
            with patch.object(layers, 'ROOT', root), patch.dict(os.environ, {'AGENT_WORKSHOP_PRACTICE': '1'}), \
                 patch.object(layers.subprocess, 'run', return_value=completed) as run:
                layers.compose(1, 'ps')
                arguments = run.call_args.args[0]
                self.assertEqual(arguments[arguments.index('--project-name') + 1], 'devdays-agent-practice-01')
                self.assertEqual(arguments[arguments.index('-f') + 1], str(config))

    def test_child_checks_inherit_practice_selection(self):
        completed = subprocess.CompletedProcess([], 0)
        with patch.dict(os.environ, {'AGENT_WORKSHOP_PRACTICE': '1'}), \
             patch.object(layers.subprocess, 'run', return_value=completed) as run:
            layers.test(7)
            self.assertEqual(run.call_args.kwargs['env']['AGENT_WORKSHOP_PRACTICE'], '1')
            self.assertEqual(run.call_args.kwargs['env']['AGENT_WORKSHOP_STAGE'], '7')

    def test_deployment_failure_cannot_report_pass(self):
        with patch.object(layers, 'up', side_effect=SystemExit(1)), \
             patch.object(layers, 'test') as test, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertFalse(layers.check(4))
            test.assert_not_called()
            self.assertIn('FAIL', output.getvalue())
            self.assertNotIn('PASS', output.getvalue())


if __name__ == '__main__':
    unittest.main()
