import tempfile
import unittest
from pathlib import Path
from clip_classifier import aggregate, collect_images


class RoutingTests(unittest.TestCase):
    def test_object(self):
        self.assertEqual(aggregate([[.9, .05, .05]] * 4)['recommended_model'], 'FreeSplatter-O')

    def test_scene_subtypes_can_disagree(self):
        result = aggregate([[.1, .8, .1], [.1, .1, .8]])
        self.assertEqual(result['recommended_model'], 'Depth Anything 3')

    def test_scene_label_matches_route(self):
        result = aggregate([[.39, .31, .30]])
        self.assertEqual(result['route'], 'scene')
        self.assertEqual(result['label'], 'room')

    def test_mixed_set_is_not_hidden_by_average(self):
        self.assertEqual(aggregate([[.99, .005, .005]] * 3 + [[.01, .98, .01]])['route'], 'uncertain')

    def test_ambiguous(self):
        self.assertIsNone(aggregate([[.5, .3, .2]])['recommended_model'])

    def test_invalid(self):
        for rows in ([], [[float('nan'), 0, 1]], [[1, 1, 1]], [[-1, 1, 1]]):
            with self.assertRaises(ValueError):
                aggregate(rows)

    def test_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'b.JPG').touch()
            (path / 'a.png').touch()
            (path / 'ignore.txt').touch()
            self.assertEqual([p.name for p in collect_images([path, path / 'a.png'])], ['a.png', 'b.JPG'])
            with self.assertRaises(ValueError):
                collect_images([path / 'missing.jpg'])


if __name__ == '__main__':
    unittest.main()
