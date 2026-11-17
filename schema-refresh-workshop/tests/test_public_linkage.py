"""Check positive and negative linkage cases without any live personal records."""

from collections import Counter
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_public_linkage import analyse_people, directory_indexes, match_people, phone_findings, phone_values


class PublicLinkageTest(unittest.TestCase):
    def test_detects_normalised_public_identity_and_employer_candidate(self):
        names, dates = directory_indexes([('Example', 'Person', '1990-01-01')])
        result = match_people([(' EXAMPLE ', 'PERSON', '1990-01-01', ['Demo company'])],
            names, dates, Counter({('example', 'person', 'demo company'): 1}))
        self.assertEqual(result['single_directory_record_by_name_and_birth_date'], 1)
        self.assertEqual(result['name_and_employer_candidates'], 1)

    def test_masked_names_do_not_match_and_duplicate_candidates_are_not_unique(self):
        names, dates = directory_indexes([('Example', 'Person', '1990-01-01')] * 2)
        result = match_people([('Example', 'Person', '1990-01-01', []),
            ('Person anonymous', 'Person anonymous', '2020-01-01', [])], names, dates, Counter())
        self.assertEqual(result['people_checked'], 2)
        self.assertEqual(result['name_and_birth_date_candidates'], 1)
        self.assertEqual(result['single_directory_record_by_name_and_birth_date'], 0)

    def test_flags_nested_unmasked_phone_value(self):
        self.assertEqual(phone_values({'delivery': {'phone': '0612 34 567'}}), 1)
        self.assertEqual(phone_values({'delivery': {'email': 'token@example.invalid'}}), 0)

    def test_returns_every_candidate_with_public_record_and_matching_reasons(self):
        people = [{'person_id': 42, 'first_name': 'Example', 'last_name': 'Person',
                   'birth_date': '1990-01-01', 'companies': ['Demo company']}]
        directory = [{'directory_id': index, 'first_name': 'Example', 'last_name': 'Person',
                      'date_of_birth': birth} for index, birth in
                     [(1, '1990-01-01'), (2, '1990-01-01'), (3, '1991-01-01')]]
        profiles = [{'profile_id': index, 'first_name': 'Example', 'last_name': 'Person',
                     'employer_name': employer} for index, employer in
                    [(1, 'Demo company'), (2, 'DEMO COMPANY'), (3, 'Different company')]]
        result = analyse_people(people, directory, profiles)
        self.assertEqual(len(result['findings']), 5)
        self.assertEqual(result['single_directory_record_by_name_and_birth_date'], 0)
        for finding in result['findings']:
            self.assertEqual(finding['person']['person_id'], 42)
        self.assertEqual(result['findings'][0]['matched_on'], ['name', 'name_and_birth_date'])
        self.assertEqual(result['findings'][2]['matched_on'], ['name'])
        self.assertEqual(result['findings'][3]['public_table'], 'public_db.professional_profile')
        self.assertEqual(result['findings'][4]['public_record']['profile_id'], 2)

    def test_phone_details_include_values_and_exact_nested_paths(self):
        self.assertEqual(list(phone_findings({'contacts': [{'phone': '0612 34 567'},
            {'mobile_phone': '0612 34 568'}]})), [
                {'json_path': ['contacts', 0, 'phone'], 'value': '0612 34 567'},
                {'json_path': ['contacts', 1, 'mobile_phone'], 'value': '0612 34 568'}])

    def test_masked_person_has_no_detailed_candidates(self):
        people = [{'person_id': 42, 'first_name': 'Person anonymous', 'last_name': 'Person anonymous',
                   'birth_date': '2020-01-01', 'companies': []}]
        directory = [{'first_name': 'Example', 'last_name': 'Person', 'date_of_birth': '1990-01-01'}]
        self.assertEqual(analyse_people(people, directory, [])['findings'], [])


if __name__ == '__main__':
    unittest.main()
