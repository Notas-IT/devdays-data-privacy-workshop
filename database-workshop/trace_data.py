#!/usr/bin/env python3
"""Read-only linkage tracing for this workshop's private/public table graph."""
import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
TABLES = (
    ("public", "people_directory", "seed", "directory_id", "Selected public person: the starting point."),
    ("public", "professional_profile", "profiles", "profile_id", "Same public profile URL, or public name + postcode. These are candidate profiles."),
    ("public", "company_registry", "registries", "registry_id", "Employer name from candidate public profiles; company names can be ambiguous."),
    ("public", "procurement_award", "awards", "award_id", "Public company registration number → procurement award."),
    ("private", "person_identity", "people", "person_id", "Union of identity candidates from all four methods; candidate IDs are not proof of identity."),
    ("private", "employment_contract", "contracts", "contract_id", "Candidate national ID or email → contract; also checks the shared contract ID hypothesis directly."),
    ("private", "payroll_event", "payroll", "payroll_event_id", "Candidate email → payroll and bank account."),
    ("private", "benefit_claim", "claims", "claim_id", "Candidate phone → benefit claim and condition category."),
    ("private", "application_user", "users", "user_id", "Candidate email → application account and permission flags."),
    ("private", "company", "companies", "company_id", "Contract registration number OR candidate public registry number → private company financials. This can link a company independently of a person."),
)
SENSITIVE = {
    "national_id", "tax_id", "email", "employee_email", "claimant_phone", "phone",
    "salary_eur", "bonus_eur", "annual_profit_eur", "annual_revenue_eur",
    "gross_pay_eur", "bank_account", "condition_category",
}
NOTICE = (
    "This traces known links in the workshop schema for ONE public person. "
    "Matches are candidates, not confirmed identities. An ID match is a hypothesis based on the generator. "
    "Counts include all matching rows; displayed examples are limited. "
    "Connected rows combine all candidate paths and can belong to different people. "
    "No match does not prove anonymisation: other linkage methods may still work. "
    "The report reflects what the SQL role can see; it does not test API permissions or RLS protection."
)


def build_sql():
    """Only trusted, fixed graph definitions enter SQL. CLI inputs use psql quoting."""
    reports = []
    for scope, name, cte, key, explanation in TABLES:
        reports.append(f"""jsonb_build_object(
          'scope', '{scope}', 'name', '{name}',
          'count', (SELECT count(*) FROM {cte}),
          'rows', (SELECT COALESCE(jsonb_agg(to_jsonb(x)), '[]'::jsonb)
                   FROM (SELECT * FROM {cte} ORDER BY {key} LIMIT :'row_limit'::integer) x))""")
    template = (ROOT / "tracing" / "trace.sql").read_text()
    return template.replace("__TABLE_REPORTS__", "jsonb_build_array(" + ",\n".join(reports) + ")")


def esc(value):
    return html.escape(str(value), quote=True)


def row_table(rows):
    if not rows:
        return "<p>No matching rows visible to this role.</p>"
    columns = list(rows[0])
    head = "".join(f'<th class="{"sensitive" if c in SENSITIVE else ""}">{esc(c)}</th>' for c in columns)
    body = "".join("<tr>" + "".join(
        f'<td class="{"sensitive" if c in SENSITIVE else ""}">{esc(row.get(c))}</td>'
        for c in columns) + "</tr>" for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def page(title, body):
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>{esc(title)}</title><style>
body{{font:16px/1.5 system-ui,sans-serif;color:#17304b;background:#f3f6fa;max-width:1250px;margin:32px auto;padding:0 20px}}
h1,h2,h3{{line-height:1.2}} .notice,details,section{{background:white;padding:18px;margin:16px 0;border:1px solid #ccd6e2;border-radius:8px}}
.notice{{border-left:5px solid #df9b21}}summary{{cursor:pointer;font-weight:650}}
table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{text-align:left;vertical-align:top;padding:8px;border:1px solid #d2dbe5;white-space:pre-wrap;overflow-wrap:anywhere}}
th{{background:#e8eff7}}.sensitive{{background:#fff0ec}}.scroll{{overflow:auto}}code{{background:#e8eff7;padding:2px 5px}}
</style><h1>{esc(title)}</h1>{body}</html>"""


def render_trace(report):
    seed = report["seed"]
    body = f'<p>Public directory ID <b>{esc(seed["directory_id"])}</b> → <code>{esc(report["private_schema"])}</code></p>'
    body += f'<div class="notice">{esc(NOTICE)}</div>'
    body += f'<p>Generated {esc(report["generated_at"])}. Database: {esc(report["database"])}; SQL role: {esc(report["database_user"])}; role flags: {esc(report["role"])}.</p>'
    body += '<h2>1. Starting public record</h2>' + row_table([seed])
    body += '<h2>2. Candidate matching paths</h2>'
    method_rows = []
    for method in report["methods"]:
        count = method["candidate_count"]
        method_rows.append({
            "method": method["path"], "evidence": method["explanation"],
            "candidate_count": count,
            "interpretation": "No candidates" if count == 0 else "One candidate; verify" if count == 1 else "Ambiguous; verify candidates",
            "sample_candidate_ids": ", ".join(map(str, method["candidate_ids"])),
        })
    body += row_table(method_rows)
    body += '<h2>3. Follow the connected records</h2><p>Expand a table to inspect values. Shaded columns highlight selected identifiers and sensitive values, including any replacements.</p>'
    explanations = {name: explanation for _, name, _, _, explanation in TABLES}
    for table in report["tables"]:
        schema = report[f'{table["scope"]}_schema']
        body += f'<details><summary>{esc(schema)}.{esc(table["name"])} — {esc(table["count"])} matching rows; showing {len(table["rows"])}</summary>'
        body += f'<p>{esc(explanations[table["name"]])}</p>' + row_table(table["rows"]) + '</details>'
    return page("Public-to-private data trace", body)


def validate_pair(before, after):
    if before.get("format_version") != 1 or after.get("format_version") != 1:
        raise ValueError("Unsupported trace report version.")
    if before["seed"] != after["seed"]:
        raise ValueError("Compare reports for the same unchanged public starting record.")
    if before["public_schema"] != after["public_schema"] or before["database"] != after["database"]:
        raise ValueError("Compare reports from the same public schema and database.")


def render_comparison(before, after):
    validate_pair(before, after)
    body = f'<p>Public directory ID {esc(before["seed"]["directory_id"])}. Before: <code>{esc(before["private_schema"])}</code>; after: <code>{esc(after["private_schema"])}</code>.</p>'
    body += f'<div class="notice">{esc(NOTICE)} Different counts may also result from changed source data, broken joins, or different SQL role permissions. A disappearing path alone is not a privacy pass.</div>'
    methods_after = {m["path"]: m for m in after["methods"]}
    rows = [{"method": m["path"], "before_candidates": m["candidate_count"],
             "after_candidates": methods_after[m["path"]]["candidate_count"]} for m in before["methods"]]
    body += '<h2>Candidate counts</h2>' + row_table(rows)
    body += '<h2>Inspect before and after values</h2><p>Rows are separate samples ordered by each table’s own ID. Matching row positions or IDs do not establish that they represent the same person.</p>'
    tables_after = {(t["scope"], t["name"]): t for t in after["tables"]}
    for old in before["tables"]:
        new = tables_after[(old["scope"], old["name"])]
        body += f'<details><summary>{esc(old["scope"])}.{esc(old["name"])} — before {esc(old["count"])}; after {esc(new["count"])}</summary>'
        body += f'<h3>Before — showing {len(old["rows"])}</h3>' + row_table(old["rows"])
        body += f'<h3>After — showing {len(new["rows"])}</h3>' + row_table(new["rows"]) + '</details>'
    body += '<section><h2>Student questions</h2><ol><li>Which paths still produce candidates, and why?</li><li>Can you distinguish the correct candidate from a collision using the public evidence?</li><li>Are salary, profit, bank details or claim categories still visible, or replaced?</li><li>Did a missing result come from privacy protection or broken relationships?</li><li>Which analytics still work? Check separately; this trace does not measure utility.</li></ol><p>Confirm claimed person matches against the instructor’s original data or protected mapping after the exercise. Keep that mapping out of the student’s linkage attempt.</p></section>'
    return page("Before / after linkage comparison", body)


def write_reports(directory, json_name, html_name, data, rendered):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, content in ((json_name, json.dumps(data, indent=2, ensure_ascii=False) + "\n"), (html_name, rendered)):
        # mkstemp creates mode 0600; replace also keeps previously existing reports private.
        fd, temp_name = tempfile.mkstemp(prefix=".trace-", dir=directory)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(content)
            os.replace(temp_name, directory / name)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    print(f"HTML: {(directory / html_name).resolve()}")
    print(f"JSON: {(directory / json_name).resolve()}")


def trace(args):
    command = ["docker", "compose", "-f", str(args.compose_file)]
    if args.project_name:
        command += ["-p", args.project_name]
    command += ["exec", "-T", args.service, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
                "-U", args.db_user, "-d", args.database,
                "-v", f"private_schema={args.private_schema}", "-v", f"public_schema={args.public_schema}",
                "-v", f"person_id={args.person if args.person is not None else ''}", "-v", f"row_limit={args.limit}"]
    result = subprocess.run(command, input=build_sql(), text=True, capture_output=True, timeout=75)
    if result.returncode:
        raise ValueError("Database trace failed. Start Postgres and check schema names, columns and read permissions.\n" + result.stderr.strip())
    report = json.loads(result.stdout)
    if report["seed"] is None:
        raise ValueError("No public directory record found. Check --person or load the workshop dataset.")
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    write_reports(args.output_dir, "trace.json", "trace.html", report, render_trace(report))
    for method in report["methods"]:
        print(f'{method["path"]}: {method["candidate_count"]} candidates')


def bounded_limit(value):
    value = int(value)
    if not 1 <= value <= 100:
        raise argparse.ArgumentTypeError("Use a limit between 1 and 100.")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    command = sub.add_parser("trace", help="Trace one public person into a selected private schema.")
    command.add_argument("--person", type=int, help="Public directory_id; defaults to the first public record.")
    command.add_argument("--private-schema", default="private_db")
    command.add_argument("--public-schema", default="public_db")
    command.add_argument("--limit", type=bounded_limit, default=10, help="Displayed rows per method/table (1–100); counts are not limited.")
    command.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "trace")
    command.add_argument("--compose-file", type=Path, default=ROOT / "docker-compose.yml")
    command.add_argument("--project-name")
    command.add_argument("--service", default="postgres")
    command.add_argument("--database", default="privacy_workshop")
    command.add_argument("--db-user", default="workshop")
    compare = sub.add_parser("compare", help="Compare two saved reports without querying the database.")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "comparison")
    args = parser.parse_args(argv)
    try:
        if args.action == "trace":
            trace(args)
        else:
            before, after = json.loads(args.before.read_text()), json.loads(args.after.read_text())
            rendered = render_comparison(before, after)
            write_reports(args.output_dir, "comparison.json", "comparison.html", {"before": before, "after": after}, rendered)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
