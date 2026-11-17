"""Read-only linkage checks; print every candidate and residual phone finding."""

from collections import Counter, defaultdict
import json
import os

import psycopg
from psycopg.rows import dict_row


def normalise(value):
    return ' '.join(str(value).casefold().split()) if value is not None else ''


def directory_indexes(rows):
    names, dates = Counter(), Counter()
    for first, last, birth in rows:
        name = (normalise(first), normalise(last))
        if all(name):
            names[name] += 1
            if birth is not None:
                dates[(*name, str(birth))] += 1
    return names, dates


def match_people(people, names, dates, employers):
    result = {'people_checked': len(people), 'name_candidates': 0,
              'name_and_birth_date_candidates': 0,
              'single_directory_record_by_name_and_birth_date': 0,
              'name_and_employer_candidates': 0}
    for first, last, birth, companies in people:
        name = (normalise(first), normalise(last))
        date_matches = dates[(*name, str(birth))] if birth is not None else 0
        result['name_candidates'] += int(names[name] > 0)
        result['name_and_birth_date_candidates'] += int(date_matches > 0)
        result['single_directory_record_by_name_and_birth_date'] += int(date_matches == 1)
        result['name_and_employer_candidates'] += int(any(
            employers[(*name, normalise(company))] > 0 for company in companies))
    return result


def read_people(dsn):
    with psycopg.connect(dsn, options='-c default_transaction_read_only=on', row_factory=dict_row) as connection:
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return connection.execute('''SELECT p.person_id, p.first_name, p.last_name, p.birth_date,
            coalesce(array_agg(DISTINCT c.company_name)
                     FILTER (WHERE c.company_name IS NOT NULL), ARRAY[]::text[]) AS companies
            FROM business.people p
            LEFT JOIN business.employment e ON e.employee_email=p.email
            LEFT JOIN business.companies c ON c.company_id=e.company_id
            GROUP BY p.person_id ORDER BY p.person_id''').fetchall()


def phone_findings(value, path=()):
    if isinstance(value, dict):
        for key, item in sorted(value.items()):
            location = (*path, key)
            if ('phone' in str(key).casefold() and isinstance(item, str)
                    and sum(character.isdigit() for character in item) >= 7):
                yield {'json_path': list(location), 'value': item}
            yield from phone_findings(item, location)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from phone_findings(item, (*path, index))


def phone_values(value):
    return sum(1 for _ in phone_findings(value))


def linkage_findings(people, directory, profiles):
    """One finding per matching public row, with all applicable matching reasons."""
    directory_by_name, profiles_by_name = defaultdict(list), defaultdict(list)
    for record in directory:
        directory_by_name[(normalise(record['first_name']), normalise(record['last_name']))].append(record)
    for record in profiles:
        profiles_by_name[(normalise(record['first_name']), normalise(record['last_name']))].append(record)
    for person in people:
        name = (normalise(person['first_name']), normalise(person['last_name']))
        if not all(name):
            continue
        for record in directory_by_name[name]:
            reasons = ['name']
            if person['birth_date'] is not None and str(person['birth_date']) == str(record['date_of_birth']):
                reasons.append('name_and_birth_date')
            yield {'person': person, 'matched_on': reasons,
                   'public_table': 'public_db.people_directory', 'public_record': record}
        companies = {normalise(company) for company in person['companies']}
        for record in profiles_by_name[name]:
            if normalise(record['employer_name']) in companies:
                yield {'person': person, 'matched_on': ['name_and_employer'],
                       'public_table': 'public_db.professional_profile', 'public_record': record}


def analyse_people(people, directory, profiles):
    names, dates = directory_indexes([(row['first_name'], row['last_name'], row['date_of_birth'])
                                      for row in directory])
    employers = Counter((normalise(row['first_name']), normalise(row['last_name']),
                         normalise(row['employer_name'])) for row in profiles)
    summary = match_people([(row['first_name'], row['last_name'], row['birth_date'], row['companies'])
                            for row in people], names, dates, employers)
    return {**summary, 'findings': list(linkage_findings(people, directory, profiles))}


def main():
    with psycopg.connect(os.environ['PUBLIC_DSN'], options='-c default_transaction_read_only=on',
                        row_factory=dict_row) as public:
        public.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        directory = public.execute('''SELECT directory_id, first_name, last_name, date_of_birth,
            city, postcode, public_profile_url
            FROM public_db.people_directory ORDER BY directory_id''').fetchall()
        profiles = public.execute('''SELECT profile_id, first_name, last_name, employer_name,
            city, postcode, role_title, public_profile_url
            FROM public_db.professional_profile ORDER BY profile_id''').fetchall()
    if not directory or not profiles:
        raise ValueError('Public reference tables are empty; linkage check is inconclusive')
    original = analyse_people(read_people(os.environ['SOURCE_DSN']), directory, profiles)
    pseudo = analyse_people(read_people(os.environ['PSEUDO_PROD_DSN']), directory, profiles)
    with psycopg.connect(os.environ['PSEUDO_PROD_DSN'], options='-c default_transaction_read_only=on') as target:
        remaining_phones = [
            {'table': 'business.people', 'person_id': person_id, 'column': 'payload', **finding}
            for person_id, payload in target.execute(
                'SELECT person_id, payload FROM business.people WHERE payload IS NOT NULL ORDER BY person_id')
            for finding in phone_findings(payload)]
    print(json.dumps({'public_directory_records': len(directory), 'public_profile_records': len(profiles),
        'original_baseline': original, 'pseudo_prod': pseudo,
        'remaining_phone_like_values_in_payload': len(remaining_phones),
        'remaining_phone_findings': remaining_phones}, indent=2, default=str, ensure_ascii=False))
    if remaining_phones:
        print('REVIEW: phone-like values remain in the pseudo-prod payload; see findings above.')
    if not original['people_checked'] or not pseudo['people_checked']:
        print('INCONCLUSIVE: a workshop people table is empty.')
        return 2
    if any(pseudo[key] for key in ('name_candidates', 'name_and_birth_date_candidates',
                                  'name_and_employer_candidates')):
        print('REVIEW: public-record linkage candidates found; matching alone does not confirm identity.')
        return 1
    print('No pseudo-prod candidates found by name, name + birth date, or name + employer.')
    if not any(original[key] for key in ('name_candidates', 'name_and_birth_date_candidates',
                                       'name_and_employer_candidates')):
        print('INCONCLUSIVE: even the original has no matches. These fixtures do not demonstrate protection against linkage.')
        return 2
    print('The tested links were removed; this is not proof against other identification methods.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
