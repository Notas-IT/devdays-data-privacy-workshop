"""Prove that catalogue ordering cannot change the generated description."""

from itertools import permutations
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from describe_schema import render_schema


class SchemaDescriptionTest(unittest.TestCase):
    def test_tables_and_columns_are_sorted_for_every_input_order(self):
        rows = [('business', 'zebra', 'id', 'bigint'),
                ('business', 'alpha', 'z_value', 'numeric(12,2)'),
                ('business', 'alpha', 'a_value', 'character varying(30)')]
        expected = ('business.alpha\n'
                    '  a_value: character varying(30)\n'
                    '  z_value: numeric(12,2)\n\n'
                    'business.zebra\n'
                    '  id: bigint\n')
        for ordering in permutations(rows):
            with self.subTest(ordering=ordering):
                self.assertEqual(render_schema(ordering), expected)

    def test_empty_table_and_empty_database_are_supported(self):
        self.assertEqual(render_schema([('business', 'empty_table', None, None)]),
                         'business.empty_table\n')
        self.assertEqual(render_schema([]), '')


if __name__ == '__main__':
    unittest.main()
