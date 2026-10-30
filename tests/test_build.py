import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('build_helper', Path(__file__).parents[1] / 'lib/build.py')
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class ContainerBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.package = {'scripts': {'build': 'astro build'}, 'dependencies': {'astro': '^7.4.2'}}
        self.write_package()
        (self.project / 'package-lock.json').write_text('{}')

    def write_package(self):
        (self.project / 'package.json').write_text(json.dumps(self.package))

    def fake_astro(self):
        path = self.project / 'node_modules/astro/package.json'
        path.parent.mkdir(parents=True)
        path.write_text('{"version":"7.4.2"}')

    def test_missing_adapter_accepted_only_with_container_preparation(self):
        helper.check(self.project, '.', prepare=True)
        with self.assertRaisesRegex(ValueError, 'Node-Adapter fehlt'):
            helper.check(self.project, '.')

    def test_non_astro_project_not_converted(self):
        self.package['dependencies'] = {'vite': '^7.0.0'}
        self.write_package()
        with self.assertRaisesRegex(ValueError, 'astro fehlt'):
            helper.check(self.project, '.', prepare=True)

    def test_auto_mode_keeps_static_build_without_adapter_or_overlay(self):
        helper.check(self.project, '.', mode='auto')
        original = "export default {output:'static'};"
        config = self.project / 'astro.config.mjs'
        config.write_text(original)
        def simulate_npm(project, args, stage):
            if stage == 'build':
                self.assertEqual(args, ['run', 'build'])
                (project / 'dist').mkdir()
                (project / 'dist/index.html').write_text('prerendered')
        with patch.object(helper, 'npm', side_effect=simulate_npm) as npm:
            helper.build(self.project, adapter='11.1.9', mode='auto')
        self.assertFalse(any(call.args[2] == 'adapter' for call in npm.call_args_list))
        self.assertFalse((self.project / '.astrodeploy.config.mjs').exists())
        self.assertEqual(config.read_text(), original)

    def test_custom_build_script_not_silently_replaced(self):
        self.package['scripts']['build'] = 'custom-build && astro build'
        self.write_package()
        with self.assertRaisesRegex(ValueError, 'Buildskript'):
            helper.check(self.project, '.', prepare=True)

    def test_npm_check_before_build_is_supported_and_preserved(self):
        self.package['scripts']['build'] = 'npm run check && astro build'
        self.package['scripts']['check'] = 'astro check'
        self.write_package()
        helper.check(self.project, '.', prepare=True)
        self.package['dependencies']['@astrojs/node'] = '^11.0.0'
        self.write_package()
        def simulate_npm(project, args, stage):
            if stage == 'build':
                # The original npm script must run, including its preceding check.
                package = json.loads((project / 'package.json').read_text())
                self.assertEqual(package['scripts']['build'], 'npm run check && astro build')
                self.assertEqual(args[:2], ['run', 'build'])
                self.assertEqual(args[2:], ['--', '--config', '.astrodeploy.config.mjs'])
                entry = project / 'dist/server/entry.mjs'
                entry.parent.mkdir(parents=True)
                entry.touch()
        with patch.object(helper, 'npm', side_effect=simulate_npm):
            helper.build(self.project, '11.1.9')

    def test_multiple_preparation_tasks_and_astro_check_are_supported(self):
        for script in ('astro check && astro build',
                       'npm run generate && npm run check && astro build',
                       '  npm run check&&astro build  '):
            with self.subTest(script=script):
                self.assertTrue(helper.supports_container_build(script))

    def test_config_arguments_cannot_land_on_a_following_command(self):
        for script in ('astro build && npm run upload', 'astro build; echo done',
                       'echo "astro build"', 'npm run check || astro build',
                       'astro build --config other.mjs', 'npm run check\nastro build'):
            with self.subTest(script=script):
                self.assertFalse(helper.supports_container_build(script))

    def test_original_config_is_not_rewritten(self):
        config = self.project / 'astro.config.mjs'
        original = "export default {site:'https://example.invalid'};\n"
        config.write_text(original)
        helper.prepare_configuration(self.project)
        self.assertEqual(config.read_text(), original)

    def test_ambiguous_configuration_is_rejected(self):
        for name in ('astro.config.mjs', 'astro.config.ts'):
            (self.project / name).write_text('export default {};')
        with self.assertRaises(helper.BuildError):
            helper.prepare_configuration(self.project)

    def test_adapter_install_pins_original_astro_and_runs_build(self):
        self.fake_astro()
        def simulate_npm(project, args, stage):
            if stage == 'build':
                entry = project / 'dist/server/entry.mjs'
                entry.parent.mkdir(parents=True)
                entry.touch()
        with patch.object(helper, 'npm', side_effect=simulate_npm) as npm:
            helper.build(self.project, '11.1.9')
        install = next(call.args[1] for call in npm.call_args_list if call.args[2] == 'adapter')
        self.assertIn('astro@7.4.2', install)
        self.assertIn('@astrojs/node@11.1.9', install)
        self.assertIn('--strict-peer-deps', install)

    def test_adapter_failure_prevents_build(self):
        self.fake_astro()
        def simulate_npm(project, args, stage):
            if stage == 'adapter':
                raise helper.BuildError(stage)
        with patch.object(helper, 'npm', side_effect=simulate_npm) as npm:
            with self.assertRaises(helper.BuildError):
                helper.build(self.project, '11.1.9')
        self.assertFalse(any(call.args[2] == 'build' for call in npm.call_args_list))

    def test_existing_adapter_is_not_reinstalled(self):
        self.package['dependencies']['@astrojs/node'] = '^11.0.0'
        self.write_package()
        def simulate_npm(project, args, stage):
            if stage == 'build':
                entry = project / 'dist/server/entry.mjs'
                entry.parent.mkdir(parents=True)
                entry.touch()
        with patch.object(helper, 'npm', side_effect=simulate_npm) as npm:
            helper.build(self.project, '11.1.9')
        self.assertFalse(any(call.args[2] == 'adapter' for call in npm.call_args_list))

    def test_npm_output_is_not_exposed_on_failure(self):
        with patch.object(helper.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['npm'], output='secret')) as run:
            with self.assertRaises(helper.BuildError) as caught:
                helper.npm(self.project, ['ci'], 'dependencies')
        self.assertEqual(str(caught.exception), 'dependencies')
        self.assertEqual(run.call_args.kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs['stderr'], subprocess.DEVNULL)

    @unittest.skipUnless(shutil.which('node'), 'Node.js für JS-Konfigurationsprüfung benötigt')
    def test_overlay_preserves_integrations_and_sets_standalone(self):
        (self.project / 'astro.config.mjs').write_text(
            "export default {site:'https://example.invalid', integrations:['existing'], build:{assets:'custom-assets'}};")
        adapter = self.project / 'node_modules/@astrojs/node'
        adapter.mkdir(parents=True)
        (adapter / 'package.json').write_text('{"type":"module","exports":"./index.mjs"}')
        (adapter / 'index.mjs').write_text('export default (options) => ({name:"test-adapter", mode:options.mode});')
        overlay = helper.prepare_configuration(self.project)
        script = 'const {default:c} = await import(process.argv[1]); console.log(JSON.stringify(c));'
        result = subprocess.run(['node', '--input-type=module', '-e', script, (self.project / overlay).as_uri()],
                                check=True, capture_output=True, text=True)
        config = json.loads(result.stdout)
        self.assertEqual(config['site'], 'https://example.invalid')
        self.assertEqual(config['integrations'], ['existing'])
        self.assertEqual(config['build']['assets'], 'custom-assets')
        self.assertEqual(config['adapter']['mode'], 'standalone')
        self.assertEqual(config['output'], 'server')


if __name__ == '__main__':
    unittest.main()
