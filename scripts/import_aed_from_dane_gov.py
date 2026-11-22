#!/usr/bin/env python3
"""Bounded public AED discovery and additive MCOD import. No schema changes."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.aed_import_http import Client, ImportBlocked

API = "https://api.dane.gov.pl"
TERMS = ["AED", "defibrylator", "defibrylatory",
         "automatyczny defibrylator zewnętrzny", "lokalizacje AED"]
REPORT = Path("reports/aed_import_report.json")
MANIFEST = Path("reports/aed_import_manifest.json")


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(temp), str(path))


def relevant(attrs):
    text = html.unescape(re.sub("<[^>]+>", " ", " ".join(
        str(attrs.get(k, "")) for k in ("title", "notes", "description", "keywords")
    )))
    return bool(re.search(r"\bAED\b|defibrylat", text, re.I))


def discover(client):
    candidates, searches = {}, []
    for term in TERMS:
        count = 0
        for obj in client.pages(API + "/datasets", {"q": term}):
            count += 1
            if relevant(obj["attributes"]):
                candidates[obj["id"]] = obj
        searches.append({"term": term, "returned": count})
    result = []
    for source_id in sorted(candidates, key=int):
        dataset = client.json(API + "/datasets/" + source_id)["data"]
        if not relevant(dataset["attributes"]):
            continue
        institution_id = dataset["relationships"]["institution"]["data"]["id"]
        institution = client.json(API + "/institutions/" + institution_id)["data"]
        resources = list(client.pages(API + "/datasets/" + source_id + "/resources", {}))
        result.append({"institution": institution, "dataset": dataset, "resources": resources})
    return result, searches


def assess(bundle, max_file, max_total):
    accepted, rejected = [], []
    for resource in bundle["resources"]:
        a = resource["attributes"]
        size = a.get("file_size")
        reason = None
        if not relevant(a):
            reason = "Resource metadata does not establish AED relevance"
        elif str(a.get("format", "")).lower() not in ("csv", "xlsx", "json", "geojson", "xml"):
            reason = "Unsupported format"
        elif not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            reason = "Unknown file size; no download authorized"
        elif size > max_file:
            reason = "Per-file size limit exceeded"
        elif not str(a.get("file_url", "")).startswith("https://"):
            reason = "No HTTPS file URL"
        if reason:
            rejected.append({"source_resource_id": resource["id"], "reason": reason})
        else:
            accepted.append(resource)
    total = sum(r["attributes"]["file_size"] for r in accepted)
    return {"dataset_id": bundle["dataset"]["id"], "files": accepted, "skipped": rejected,
            "known_bytes": total, "eligible": bool(accepted) and total <= max_total}


def snapshot():
    """Fingerprint application sources and PostgreSQL schema, never row values."""
    from django.db import connection
    digest = hashlib.sha256()
    for path in sorted(Path("mcod").rglob("*")):
        if path.is_file() and "__pycache__" not in str(path) and path.suffix != ".pyc":
            digest.update(str(path).encode())
            digest.update(path.read_bytes())
    with connection.cursor() as cursor:
        cursor.execute("""SELECT table_name,column_name,data_type,is_nullable,column_default
          FROM information_schema.columns WHERE table_schema='public'
          ORDER BY table_name,ordinal_position""")
        columns = cursor.fetchall()
        cursor.execute("""SELECT tablename,indexname,indexdef FROM pg_indexes
          WHERE schemaname='public' ORDER BY tablename,indexname""")
        indexes = cursor.fetchall()
        cursor.execute("""SELECT conrelid::regclass::text, conname,pg_get_constraintdef(oid)
          FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY 1,2""")
        constraints = cursor.fetchall()
    from mcod.organizations.models import Organization
    from mcod.datasets.models import Dataset
    from mcod.resources.models import Resource
    from django.contrib.auth import get_user_model
    return {
        "mcod_code_sha256": digest.hexdigest(),
        "schema_sha256": hashlib.sha256(json.dumps(
            [columns, indexes, constraints], default=str).encode()).hexdigest(),
        "counts": {"institutions": Organization.objects.count(), "datasets": Dataset.objects.count(),
                   "resources": Resource.objects.count(), "users": get_user_model().objects.count()},
    }


def report_markdown(report):
    lines = ["# Import publicznych danych AED", "", "Status: **{}**".format(report["status"]), "",
             "Data UTC: " + report["timestamp"], "",
             "## Wyniki", "```json", json.dumps(report.get("counts", {}), ensure_ascii=False, indent=2),
             "```", "", "## Błędy i blokady"]
    lines += ["- " + str(e) for e in report.get("errors", [])] or ["- Brak."]
    lines += ["", "## Znalezione źródła",
              "| ID zbioru | Tytuł | ID instytucji | ID zasobów | Znane bajty kwalifikujących się plików |",
              "|---|---|---|---|---|"]
    for item in report.get("discovery", []):
        lines.append("| {} | {} | {} | {} | {} |".format(
            item["source_dataset_id"], item["title"].replace("|", "/"),
            item["source_institution_id"], ", ".join(item["resource_ids"]), item["known_bytes"]))
    lines += ["", "Znane bajty pochodzą z metadanych API, nie z pobranych plików.",
              "Brak rozmiaru nie oznacza pliku o zerowej wielkości.",
              "", "## Kontrole", "```json",
              json.dumps(report.get("verification", {}), ensure_ascii=False, indent=2), "```",
              "", "## Importowane identyfikatory", "```json",
              json.dumps(report.get("imported", {}), ensure_ascii=False, indent=2), "```",
              "", "## Zakres i ograniczenia", report.get("discovery_scope", ""),
              "", "Skrypt zatrzymał się na oryginalnych walidatorach. Etap zapisu pozostaje zablokowany.",
              "Nie wykonano pilota, testu idempotencji ani testu API importowanych zasobów.",
              "Nie wykonano importu pozostałych zbiorów. Liczby wierszy plików nie są liczbą unikalnych AED."]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--import", dest="do_import", action="store_true")
    modes.add_argument("--report", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit-datasets", type=int, default=1)
    parser.add_argument("--dataset-id")
    parser.add_argument("--max-file-bytes", type=int, default=10 * 1024 * 1024)
    parser.add_argument("--max-total-bytes", type=int, default=25 * 1024 * 1024)
    args = parser.parse_args()
    if args.report:
        report = json.loads(REPORT.read_text())
        REPORT.with_suffix(".md").write_text(report_markdown(report), encoding="utf-8")
        print(json.dumps({"status": report["status"], "counts": report.get("counts"),
                          "errors": report.get("errors")}, ensure_ascii=False))
        return
    if args.limit_datasets != 1:
        parser.error("Only the approved one-dataset pilot is enabled.")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mcod.settings.replit")
    import django
    django.setup()
    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "status": "started",
              "errors": [], "verification": {}, "imported": {}, "counts": {
                  "imported_institutions": 0, "imported_datasets": 0, "imported_resources": 0,
                  "downloaded_files_this_run": 0, "downloaded_bytes_this_run": 0,
                  "aed_rows_counted": None,
              },
              "limits": {"file_bytes": args.max_file_bytes, "total_bytes": args.max_total_bytes}}
    before = snapshot()
    try:
        client = Client(args.max_file_bytes, args.max_total_bytes)
        cache = Path("reports/aed_discovery.json")
        if args.resume and cache.exists():
            discovery = json.loads(cache.read_text())
        else:
            bundles, searches = discover(client)
            discovery = {"bundles": bundles, "searches": searches, "timestamp": report["timestamp"]}
            atomic_json(cache, discovery)
        bundles = discovery["bundles"]
        report["counts"].update({
            "found_institutions": len({b["institution"]["id"] for b in bundles}),
            "found_datasets": len(bundles),
            "found_resources": sum(len(b["resources"]) for b in bundles),
        })
        assessments = [assess(b, args.max_file_bytes, args.max_total_bytes) for b in bundles]
        report["discovery"] = [
            {"source_dataset_id": b["dataset"]["id"], "title": b["dataset"]["attributes"]["title"],
             "source_institution_id": b["institution"]["id"], "resource_ids": [r["id"] for r in b["resources"]],
             "eligible": a["eligible"], "known_bytes": a["known_bytes"], "skipped": a["skipped"]}
            for b, a in zip(bundles, assessments)]
        choices = [(b, a) for b, a in zip(bundles, assessments)
                   if a["eligible"] and (not args.dataset_id or b["dataset"]["id"] == args.dataset_id)]
        if not choices:
            raise ImportBlocked("No eligible dataset with known bounded file sizes.")
        bundle, assessment = min(choices, key=lambda pair: pair[1]["known_bytes"])
        report["selected_dataset"] = bundle["dataset"]["id"]
        report["selected_source_ids"] = {
            "institution": bundle["institution"]["id"],
            "dataset": bundle["dataset"]["id"],
            "resources": [r["id"] for r in assessment["files"]],
        }
        report["verification"]["import_api_tests"] = "not_run_no_import"
        from scripts.aed_import_models import preflight, import_bundle
        prepared = preflight(bundle, assessment)
        if args.dry_run:
            report["status"] = "dry_run_passed"
        else:
            previous = json.loads(REPORT.read_text()) if REPORT.exists() else {}
            if previous.get("status") not in ("dry_run_passed", "imported") or previous.get(
                    "selected_dataset") != bundle["dataset"]["id"]:
                raise ImportBlocked("Run a successful dry-run for the selected dataset before importing.")
            report["imported"] = import_bundle(bundle, assessment, prepared, client, MANIFEST, args.resume)
            report["status"] = "imported"
        report["counts"].update({"downloaded_files_this_run": client.downloads,
                                 "downloaded_bytes_this_run": client.downloaded_bytes})
    except Exception as exc:
        report["status"] = "blocked"
        report["errors"].append("{}: {}".format(type(exc).__name__, exc))
    finally:
        if "client" in locals():
            report["counts"].update({"downloaded_files_this_run": client.downloads,
                                     "downloaded_bytes_this_run": client.downloaded_bytes})
        after = snapshot()
        report["verification"].update({
            "code_unchanged": before["mcod_code_sha256"] == after["mcod_code_sha256"],
            "schema_unchanged": before["schema_sha256"] == after["schema_sha256"],
            "before": before, "after": after,
        })
        report["discovery_scope"] = (
            "Five requested keyword searches with ID-cursor pagination, then AED/defibrylat "
            "matching in public metadata. This does not prove detection of every "
            "unlabelled or otherwise unsearchable AED dataset."
        )
        atomic_json(REPORT, report)
        REPORT.with_suffix(".md").write_text(report_markdown(report), encoding="utf-8")
        print(json.dumps({"status": report["status"], "counts": report["counts"],
                          "selected_dataset": report.get("selected_dataset"),
                          "errors": report["errors"]}, ensure_ascii=False))
    if report["status"] == "blocked":
        sys.exit(2)


if __name__ == "__main__":
    main()
