import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine'))
import render


class CacheBudgetTests(unittest.TestCase):
    def test_under_budget_never_reads_project_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cached = root / 'frames/frame-0-0.jpg'
            cached.parent.mkdir()
            cached.write_bytes(b'x' * 100)
            with patch.object(Path, 'read_text', side_effect=AssertionError('Unneeded manifest read')):
                self.assertEqual(render.maintain_cache(root, 5), {'bytes': 100, 'removed': 0})
            self.assertTrue(cached.exists())

    def test_over_budget_still_defers_cleanup_for_unreadable_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cached = root / 'frames/frame-0-0.jpg'
            cached.parent.mkdir()
            cached.write_bytes(b'x' * 100)
            (root / 'unreadable.studio').write_text('invalid JSON')
            with patch.object(render, 'ROOT', root / 'isolated-editor'):
                result = render.maintain_cache(root, 0)
            self.assertTrue(result['deferred'])
            self.assertEqual(result['removed'], 0)
            self.assertTrue(cached.exists())


if __name__ == '__main__':
    unittest.main()
