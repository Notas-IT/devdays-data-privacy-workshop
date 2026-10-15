"""Fictional Lithuanian events; unknown nested fields deliberately contain PII."""

PEOPLE = [
    {"employee_name": "Ąžuolas Žukauskas", "national_id": "39001010011",
     "email": "azuolas@example.com", "phone": "0612 34 567",
     "address": "Žalgirio g. 18-7, Vilnius", "salary_eur": 4250,
     "company_profit_eur": 847321},
    {"employee_name": "Ūla Šimkutė", "national_id": "49602020022",
     "email": "ula@example.com", "phone": "069876543",
     "address": "Ąžuolų g. 5, Šiauliai", "salary_eur": 3725,
     "company_profit_eur": 965432},
]


def event(service: str, sequence: int) -> dict:
    person = PEOPLE[sequence % len(PEOPLE)]
    event_name = "salary_export" if service == "hr" else "invoice_created"
    return {
        "level": "INFO", "event": event_name, "sequence": sequence,
        "message": (
            f"Anketa: darbuotojas={person['employee_name']}; "
            f"asmens_kodas={person['national_id']}; "
            f"telefonas={person['phone']}; adresas={person['address']}; "
            f"el_pastas: {person['email']}; atlyginimas={person['salary_eur']} EUR; būsena=gerai"
        ),
        **person,
        "debug": {"customer": {"email": person["email"]}},
        "labels": {"employee": person["employee_name"]},
    }


def sensitive_values() -> set[str]:
    return {str(value) for person in PEOPLE for value in person.values()}
