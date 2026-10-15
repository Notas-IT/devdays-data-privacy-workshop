"""Generate deterministic synthetic Lithuanian logs with exact span annotations."""

import argparse
import json
from pathlib import Path

DEFAULT_OUTPUT = Path(__file__).parent / "examples" / "lithuanian_logs.jsonl"


def example(case_id, description, parts, *, forbidden_entities=()):
    text = "2026-10-14T09:00:00Z INFO "
    expected = []
    for part in parts:
        if isinstance(part, tuple):
            entity, value = part
            expected.append({"entity": entity, "start": len(text),
                             "end": len(text) + len(value), "value": value})
            text += value
        else:
            text += part
    return {"id": case_id, "description": description, "text": text,
            "expected": expected, "forbidden_entities": list(forbidden_entities)}


def generate_examples():
    return [
        example("personal_code", "Asmens kodas be angliško konteksto", [
            "Prisijungimas: asmens_kodas=", ("LT_PERSON_CODE", "39001010011"), "; būsena=gerai"]),
        example("personal_code_spaces", "Asmens kodas su tarpu ir dvitaškiu", [
            "Patikra: asmens kodas: ", ("LT_PERSON_CODE", "49602020022"), "; būsena=baigta"]),
        example("person_name", "Vardas su lietuviškomis raidėmis", [
            "Sesija: darbuotojas=", ("PERSON", "Ąžuolas Žukauskas"), "; veiksmas=prisijungė"]),
        example("patient_name", "Paciento vardas ir pavardė", [
            "Registracija: pacientas=", ("PERSON", "Ūla Šimkutė"), "; būsena=priimta"]),
        example("hyphenated_name", "Dviguba pavardė", [
            "Užklausa: klientas=", ("PERSON", "Živilė Kazlauskaitė-Žukienė"), "; būsena=gerai"]),
        example("address", "Gyvenamosios vietos adresas", [
            "Pristatymas: adresas=", ("LOCATION", "Žalgirio g. 18-7, Vilnius"), "; būsena=paruošta"]),
        example("address_other_city", "Kitas adresas", [
            "Siunta: gyvenamoji_vieta: ", ("LOCATION", "Ąžuolų g. 5, Šiauliai"), "; būsena=išsiųsta"]),
        example("birth_date", "Gimimo data", [
            "Anketa: gimimo_data=", ("DATE_TIME", "1990-01-01"), "; būsena=atnaujinta"]),
        example("local_phone", "Vietinis telefono formatas", [
            "Pranešimas: telefonas=", ("PHONE_NUMBER", "0612 34 567"), "; būsena=eilėje"]),
        example("compact_phone", "Telefonas be tarpų", [
            "Pranešimas: tel: ", ("PHONE_NUMBER", "069876543"), "; būsena=eilėje"]),
        example("obfuscated_email", "El. paštas su lietuviškais skirtukais", [
            "Kontaktas: el_pastas=", ("EMAIL_ADDRESS", "zivile (eta) example (taskas) invalid"), "; būsena=patikrinta"]),
        example("salary", "Atlyginimas su darbuotojo tapatybe", [
            "Algų eksportas: darbuotojas=", ("PERSON", "Ąžuolas Žukauskas"),
            "; atlyginimas=", ("LT_SALARY", "4250,00 EUR"), "; būsena=baigta"]),
        example("combined", "Keli jautrūs laukai vienoje eilutėje", [
            "Anketa: klientas=", ("PERSON", "Ūla Šimkutė"),
            "; asmens_kodas=", ("LT_PERSON_CODE", "49602020022"),
            "; adresas=", ("LOCATION", "Ąžuolų g. 5, Šiauliai"),
            "; el_pastas=", ("EMAIL_ADDRESS", "ula (eta) example (taskas) invalid"), "; būsena=gerai"]),
        example("standard_email", "Standartinis el. paštas: bazinis kontrolinis atvejis", [
            "Pranešimas: el_pastas: ", ("EMAIL_ADDRESS", "workshop@example.com"), "; būsena=eilėje"]),
        example("order_number", "Užsakymo numeris nėra asmens kodas", [
            "Užsakymas: uzsakymo_id=39001010011; būsena=baigta"], forbidden_entities=["LT_PERSON_CODE"]),
        example("public_salary_budget", "Bendras biudžetas nėra asmens atlyginimas", [
            "Ataskaita: biudzetas=4250,00 EUR; darbuotoju_skaicius=12"], forbidden_entities=["LT_SALARY"]),
        example("system_name", "Paslaugos pavadinimas nėra darbuotojo vardas", [
            "Patikra: paslauga=Žalgirio Sistema; būsena=veikia"], forbidden_entities=["PERSON"]),
        example("service_and_person", "Paslaugos kontekstas neturi slėpti darbuotojo", [
            "Patikra: paslauga=Žalgirio Sistema; darbuotojas=", ("PERSON", "Ąžuolas Žukauskas"), "; būsena=veikia"]),
        example("short_code", "Trumpas numeris nėra asmens kodas", [
            "Patikra: asmens_kodas=12345; būsena=atmesta"], forbidden_entities=["LT_PERSON_CODE"]),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cases = generate_examples()
    with args.out.open("w", encoding="utf-8") as output:
        for case in cases:
            output.write(json.dumps(case, ensure_ascii=False) + "\n")
    log_path = args.out.with_suffix(".log")
    log_path.write_text("\n".join(case["text"] for case in cases) + "\n", encoding="utf-8")
    print(f"Generated {len(cases)} synthetic cases in {args.out} and {log_path}")


if __name__ == "__main__":
    main()
