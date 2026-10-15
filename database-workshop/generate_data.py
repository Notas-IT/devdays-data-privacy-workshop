#!/usr/bin/env python3
import argparse
import csv
import hashlib
import random
from datetime import date, timedelta
from pathlib import Path


FIRST_NAMES = [
    "Aiste", "Austejas", "Darius", "Egle", "Gabija", "Ieva", "Jonas", "Justina",
    "Karolis", "Lina", "Lukas", "Mantas", "Migle", "Monika", "Paulius", "Rasa",
    "Rokas", "Ruta", "Tomas", "Viktorija", "Adomas", "Emilija", "Greta", "Simona",
]

LAST_NAMES = [
    "Kazlauskas", "Petrauskas", "Jankauskas", "Stankevicius", "Paulauskas",
    "Vasiliauskas", "Zukauskas", "Butkus", "Balciunas", "Urbonas", "Kavaliauskas",
    "Navickas", "Sakalauskas", "Mikalauskas", "Kairys", "Mockus", "Banys", "Daukantas",
]

CITIES = [
    ("Vilnius", "01"), ("Kaunas", "44"), ("Klaipeda", "92"), ("Siauliai", "76"),
    ("Panevezys", "35"), ("Alytus", "62"), ("Marijampole", "68"), ("Utena", "28"),
]

STREETS = [
    "Gedimino pr.", "Vilniaus g.", "Taikos pr.", "Laisves al.", "Maironio g.",
    "Savanoriu pr.", "Zalgirio g.", "Mindaugo g.", "Nemuno g.", "Parko g.",
]

INDUSTRIES = [
    "Technology", "Finance", "Retail", "Manufacturing", "Healthcare", "Logistics",
    "Energy", "Education", "Construction", "Professional Services",
]

ROLE_PROFILES = [
    ("Software Engineer", "Engineering", 32000, 85000),
    ("Data Analyst", "Analytics", 28000, 68000),
    ("Sales Manager", "Sales", 30000, 76000),
    ("Accountant", "Finance", 26000, 59000),
    ("HR Specialist", "People", 24000, 56000),
    ("Operations Lead", "Operations", 34000, 78000),
    ("Product Manager", "Product", 42000, 95000),
    ("Legal Counsel", "Legal", 45000, 105000),
    ("Marketing Specialist", "Marketing", 25000, 62000),
    ("Support Agent", "Support", 19000, 43000),
]

CONDITIONS = [
    "Dental", "Vision", "Cardiology", "Dermatology", "Mental Health", "Orthopedics",
    "Respiratory", "Preventive Care", "Physical Therapy", "Neurology",
]

REFERENCE_YEAR = 2026

BUYERS = [
    "City Municipality", "National Health Fund", "Road Authority", "University Network",
    "Public Energy Agency", "Digital Services Office",
]

AWARD_CATEGORIES = [
    "Software", "Consulting", "Facilities", "Training", "Equipment", "Research",
]


def stable_int(value, modulo):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) % modulo


def write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def random_date(rng, start, end):
    days = (end - start).days
    return start + timedelta(days=rng.randint(0, days))


def money_band(value):
    if value < 25000:
        return "under_25k"
    if value < 40000:
        return "25k_40k"
    if value < 60000:
        return "40k_60k"
    if value < 80000:
        return "60k_80k"
    if value < 120000:
        return "80k_120k"
    return "over_120k"


def count_band(value):
    if value < 20:
        return "1_19"
    if value < 100:
        return "20_99"
    if value < 500:
        return "100_499"
    if value < 1000:
        return "500_999"
    return "1000_plus"


def seniority_for_salary(salary):
    if salary < 30000:
        return "junior"
    if salary < 55000:
        return "mid"
    if salary < 85000:
        return "senior"
    return "executive"


def make_companies(rng, count):
    companies = []
    for company_id in range(1, count + 1):
        industry = rng.choice(INDUSTRIES)
        city, _ = rng.choice(CITIES)
        employee_count = rng.randint(12, 2600)
        revenue = employee_count * rng.randint(55000, 260000)
        margin_percent = rng.randint(-8, 28)
        profit = int(revenue * margin_percent / 100)
        companies.append({
            "company_id": company_id,
            "registration_number": f"CR{company_id:08d}",
            "company_name": f"{rng.choice(LAST_NAMES)} {industry} UAB",
            "industry": industry,
            "headquarters_city": city,
            "employee_count": employee_count,
            "annual_revenue_eur": revenue,
            "annual_profit_eur": profit,
        })
    return companies


def make_people(rng, people_count, companies):
    identities = []
    contracts = []
    payroll_events = []
    claims = []
    users = []
    public_directory = []
    professional_profiles = []

    managers = []
    base_month = date(2026, 9, 1)

    for person_id in range(1, people_count + 1):
        first_name = rng.choice(FIRST_NAMES)
        last_name = rng.choice(LAST_NAMES)
        birth = random_date(rng, date(1960, 1, 1), date(2004, 12, 31))
        city, postcode_prefix = rng.choice(CITIES)
        postcode = f"LT-{postcode_prefix}{rng.randint(100, 999)}"
        email_name = f"{first_name.lower()}.{last_name.lower()}.{person_id}"
        personal_email = f"{email_name}@example.test"
        phone = f"+3706{person_id:07d}"
        national_id = f"LT{birth:%y%m%d}{person_id:06d}"
        tax_id = f"TAX{stable_int(national_id, 10**10):010d}"
        profile_url = f"https://profiles.example.test/{email_name}"
        street = rng.choice(STREETS)

        company = companies[(person_id - 1) % len(companies)]
        role_title, department, salary_min, salary_max = rng.choice(ROLE_PROFILES)
        experience_boost = max(0, 40 - (REFERENCE_YEAR - birth.year)) * -350
        salary = max(18000, rng.randint(salary_min, salary_max) + experience_boost)
        bonus = int(salary * rng.choice([0, 0, 0.03, 0.05, 0.08, 0.12]))
        work_email = f"{email_name}@{company['registration_number'].lower()}.work.test"
        manager_email = rng.choice(managers) if managers and rng.random() < 0.88 else ""
        if rng.random() < 0.07:
            managers.append(work_email)

        identities.append({
            "person_id": person_id,
            "national_id": national_id,
            "tax_id": tax_id,
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": birth.isoformat(),
            "email": personal_email,
            "phone": phone,
            "home_street": f"{street} {rng.randint(1, 220)}",
            "home_city": city,
            "home_postcode": postcode,
        })

        contracts.append({
            "contract_id": person_id,
            "national_id": national_id,
            "employee_email": personal_email,
            "company_registration_number": company["registration_number"],
            "role_title": role_title,
            "department": department,
            "employment_start_date": random_date(rng, date(2005, 1, 1), date(2026, 9, 1)).isoformat(),
            "salary_eur": salary,
            "bonus_eur": bonus,
            "manager_email": manager_email,
        })

        for month_offset in range(3):
            gross = int((salary + bonus) / 12) + rng.randint(-120, 180)
            payroll_events.append({
                "payroll_event_id": (person_id - 1) * 3 + month_offset + 1,
                "employee_email": personal_email,
                "payroll_month": (base_month - timedelta(days=31 * month_offset)).replace(day=1).isoformat(),
                "gross_pay_eur": gross,
                "tax_withheld_eur": int(gross * rng.uniform(0.18, 0.32)),
                "bank_account": f"LT{stable_int(personal_email, 10**18):018d}",
            })

        for claim_number in range(rng.randint(0, 2)):
            claims.append({
                "claim_id": len(claims) + 1,
                "claimant_phone": phone,
                "claim_date": random_date(rng, date(2025, 1, 1), date(2026, 9, 30)).isoformat(),
                "condition_category": rng.choice(CONDITIONS),
                "provider_city": rng.choice(CITIES)[0],
                "amount_eur": rng.randint(35, 2400),
                "approved": rng.random() > 0.11,
            })

        users.append({
            "user_id": person_id,
            "email": personal_email,
            "permission_group": rng.choice(["employee", "manager", "hr", "finance", "executive"]),
            "can_view_salary": "true" if rng.random() < 0.08 else "false",
            "can_view_company_financials": "true" if rng.random() < 0.04 else "false",
        })

        public_directory.append({
            "directory_id": person_id,
            "first_name": first_name,
            "last_name": last_name,
            "date_of_birth": birth.isoformat(),
            "city": city,
            "postcode": postcode,
            "public_profile_url": profile_url,
        })

        public_postcode = postcode if rng.random() < 0.82 else f"LT-{postcode_prefix}{rng.randint(100, 999)}"
        professional_profiles.append({
            "profile_id": person_id,
            "first_name": first_name,
            "last_name": last_name,
            "city": city,
            "postcode": public_postcode,
            "employer_name": company["company_name"],
            "role_title": role_title,
            "seniority": seniority_for_salary(salary),
            "salary_band": money_band(salary),
            "public_profile_url": profile_url,
        })

    return identities, contracts, payroll_events, claims, users, public_directory, professional_profiles


def make_public_companies(companies):
    rows = []
    for company in companies:
        rows.append({
            "registry_id": company["company_id"],
            "registration_number": company["registration_number"],
            "company_name": company["company_name"],
            "industry": company["industry"],
            "city": company["headquarters_city"],
            "employee_count_band": count_band(company["employee_count"]),
            "revenue_band": money_band(company["annual_revenue_eur"]),
            "profit_band": money_band(company["annual_profit_eur"]),
        })
    return rows


def make_procurement_awards(rng, companies, award_count):
    rows = []
    for award_id in range(1, award_count + 1):
        company = rng.choice(companies)
        rows.append({
            "award_id": award_id,
            "registration_number": company["registration_number"],
            "award_date": random_date(rng, date(2024, 1, 1), date(2026, 9, 30)).isoformat(),
            "buyer_name": rng.choice(BUYERS),
            "award_category": rng.choice(AWARD_CATEGORIES),
            "award_value_eur": rng.randint(8000, 900000),
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic Postgres CSV data for privacy exercises.")
    parser.add_argument("--people", type=int, default=100000, help="Number of people to generate.")
    parser.add_argument("--companies", type=int, default=1200, help="Number of companies to generate.")
    parser.add_argument("--seed", type=int, default=20261012, help="Deterministic random seed.")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "generated", help="Output directory.")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)

    companies = make_companies(rng, args.companies)
    (
        identities,
        contracts,
        payroll_events,
        claims,
        users,
        public_directory,
        professional_profiles,
    ) = make_people(rng, args.people, companies)
    public_companies = make_public_companies(companies)
    procurement_awards = make_procurement_awards(rng, companies, max(args.companies * 2, args.people // 20))

    write_csv(args.out / "private_company.csv", companies[0].keys(), companies)
    write_csv(args.out / "private_person_identity.csv", identities[0].keys(), identities)
    write_csv(args.out / "private_employment_contract.csv", contracts[0].keys(), contracts)
    write_csv(args.out / "private_payroll_event.csv", payroll_events[0].keys(), payroll_events)
    write_csv(args.out / "private_benefit_claim.csv", claims[0].keys(), claims)
    write_csv(args.out / "private_application_user.csv", users[0].keys(), users)
    write_csv(args.out / "public_company_registry.csv", public_companies[0].keys(), public_companies)
    write_csv(args.out / "public_people_directory.csv", public_directory[0].keys(), public_directory)
    write_csv(args.out / "public_professional_profile.csv", professional_profiles[0].keys(), professional_profiles)
    write_csv(args.out / "public_procurement_award.csv", procurement_awards[0].keys(), procurement_awards)

    print(f"Generated {args.people:,} people, {len(companies):,} companies, and {len(claims):,} claims in {args.out}")


if __name__ == "__main__":
    main()
