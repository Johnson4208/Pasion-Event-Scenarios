import unittest
from pathlib import Path
from release_packages import PACKAGES, roadmap

class PackageTests(unittest.TestCase):
    def test_dependency_graph_is_resolvable_and_suites_exist(self):
        root=Path(__file__).parent
        def visit(stage,ancestors=()):
            self.assertNotIn(stage,ancestors)
            self.assertIn(stage,PACKAGES)
            for dependency in PACKAGES[stage]['dependencies']:visit(dependency,ancestors+(stage,))
        for stage,package in PACKAGES.items():
            visit(stage)
            for suite in package['tests']:self.assertTrue((root/suite).is_file(),suite)
    def test_package_inventory_does_not_imply_release(self):
        for package in roadmap():
            self.assertEqual(package['exit_gate'],'NOT_CERTIFIED')
            self.assertTrue(package['remaining'])
            self.assertEqual(package['status'],'DEFERRED' if package['stage']=='P4+' else 'GUARDED')
