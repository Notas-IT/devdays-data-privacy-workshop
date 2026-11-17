"""Replace nonessential display and financial values in pseudo-prod only."""

import argparse
import json
import os

import psycopg

from tokenize_pseudo_prod import ensure_target


def verify_masking(target, *, expected_database="pseudo-prod"):
    ensure_target(target, expected_database)
    people = target.execute('''SELECT count(*),
        count(*) FILTER (WHERE first_name IS DISTINCT FROM 'Person anonymous'),
        count(*) FILTER (WHERE last_name IS DISTINCT FROM 'Person anonymous'),
        count(*) FILTER (WHERE birth_date IS DISTINCT FROM DATE '2020-01-01')
        FROM business.people''').fetchone()
    companies = target.execute('''SELECT count(*),
        count(*) FILTER (WHERE company_name IS DISTINCT FROM 'Person anonymous'),
        count(*) FILTER (WHERE annual_profit_eur IS DISTINCT FROM 0)
        FROM business.companies''').fetchone()
    employment = target.execute('''SELECT count(*),
        count(*) FILTER (WHERE salary_eur IS DISTINCT FROM 3500)
        FROM business.employment''').fetchone()
    links = target.execute('''SELECT
        count(*) FILTER (WHERE p.person_id IS NULL),
        count(*) FILTER (WHERE c.company_id IS NULL)
        FROM business.employment AS e
        LEFT JOIN business.people AS p ON p.email=e.employee_email
        LEFT JOIN business.companies AS c ON c.company_id=e.company_id''').fetchone()
    mismatches = {'first_name': people[1], 'last_name': people[2], 'birth_date': people[3],
        'company_name': companies[1], 'annual_profit_eur': companies[2], 'salary_eur': employment[1]}
    return {'checked_rows': {'people': people[0], 'companies': companies[0], 'employment': employment[0]},
            'unmasked_values': mismatches, 'total_unmasked_values': sum(mismatches.values()),
            'orphaned_employment_email_links': links[0], 'orphaned_company_links': links[1]}


def mask_pseudo_prod(target, *, expected_database="pseudo-prod"):
    """Apply all requested constants atomically; leave HMAC identifiers unchanged."""
    ensure_target(target, expected_database)
    with target.transaction():
        target.execute("SELECT pg_advisory_xact_lock(hashtext('pseudo-prod-hmac'))")
        people = target.execute('''UPDATE business.people
            SET first_name='Person anonymous', last_name='Person anonymous', birth_date=DATE '2020-01-01'
            WHERE first_name IS DISTINCT FROM 'Person anonymous'
               OR last_name IS DISTINCT FROM 'Person anonymous'
               OR birth_date IS DISTINCT FROM DATE '2020-01-01' ''').rowcount
        companies = target.execute('''UPDATE business.companies
            SET company_name='Person anonymous', annual_profit_eur=0
            WHERE company_name IS DISTINCT FROM 'Person anonymous'
               OR annual_profit_eur IS DISTINCT FROM 0''').rowcount
        employment = target.execute('''UPDATE business.employment SET salary_eur=3500
            WHERE salary_eur IS DISTINCT FROM 3500''').rowcount
        report = verify_masking(target, expected_database=expected_database)
        if (report['total_unmasked_values'] or report['orphaned_employment_email_links']
                or report['orphaned_company_links']):
            raise ValueError('Masking or relationship validation failed; changes rolled back')
        return {**report, 'updated_rows': {'people': people, 'companies': companies, 'employment': employment}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['apply', 'verify'])
    args = parser.parse_args()
    with psycopg.connect(os.environ['PSEUDO_PROD_DSN'], autocommit=True) as target:
        if args.command == 'apply':
            report = mask_pseudo_prod(target)
        else:
            with target.transaction():
                target.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                report = verify_masking(target)
    print(json.dumps(report, indent=2))
    return int(bool(report['total_unmasked_values'] or report['orphaned_employment_email_links']
                    or report['orphaned_company_links']))


if __name__ == '__main__':
    raise SystemExit(main())
