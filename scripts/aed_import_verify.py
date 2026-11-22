"""Count source rows without changing bytes and verify the existing public API."""
import csv
import hashlib
import io
import json
import time
from urllib.parse import urlsplit

from scripts.aed_import_http import Client, ImportBlocked


def count_records(content, format_name):
    if format_name == "csv":
        for encoding in ("utf-8-sig", "cp1250"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ImportBlocked("Unknown CSV encoding.")
        if "<html" in text[:200].lower():
            raise ImportBlocked("Source returned HTML, not a CSV file.")
        # Sniffer can mistake punctuation inside long quoted descriptions for
        # the delimiter. Require a consistent multi-column parse instead.
        candidates = []
        for delimiter in (",", ";", "\t", "|"):
            try:
                rows = csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
                header = next(rows, [])
                if len(header) < 2:
                    continue
                count = 0
                for row in rows:
                    if not any(cell.strip() for cell in row):
                        continue
                    if len(row) != len(header):
                        raise csv.Error("Inconsistent column count")
                    count += 1
                candidates.append(count)
            except csv.Error:
                continue
        if len(candidates) != 1:
            raise ImportBlocked("CSV delimiter is ambiguous or rows have inconsistent widths.")
        return candidates[0]
    if format_name in ("json", "geojson"):
        data = json.loads(content)
        if isinstance(data, list):
            return len(data)
        for key in ("features", "data", "records", "results"):
            if isinstance(data.get(key), list):
                return len(data[key])
        return None
    if format_name == "xlsx":
        from zipfile import ZipFile
        from openpyxl import load_workbook
        with ZipFile(io.BytesIO(content)) as archive:
            if len(archive.infolist()) > 1000 or sum(
                    item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise ImportBlocked("XLSX expanded size exceeds the safety limit.")
        book = load_workbook(io.BytesIO(content), read_only=True, data_only=True, keep_links=False)
        try:
            rows = book.active.iter_rows(values_only=True)
            next(rows, None)
            return sum(any(v is not None for v in row) for row in rows)
        finally:
            book.close()
    if format_name == "xml":
        from defusedxml import ElementTree
        root = ElementTree.fromstring(content)
        if root.tag.lower().endswith("html"):
            raise ImportBlocked("Source returned HTML, not an XML data file.")
        members = [node for node in root.iter() if node.tag.split("}")[-1] in
                   ("featureMember", "member")]
        return len(members) if members else None
    raise ImportBlocked("Unsupported source file format.")


def verify_import(org, dataset, resource, entry, base_url, client):
    from urllib.parse import urlsplit
    # This trusted local application origin may expose Replit's preview port.
    client = Client(client.max_file, client.max_total)
    client.trusted_origin = urlsplit(base_url).netloc
    metadata_url = base_url.rstrip("/") + "/resources/" + str(resource.pk)
    for attempt in range(30):
        try:
            metadata = client.json(metadata_url)
            if str(metadata["data"]["id"]) == str(resource.pk):
                break
        except Exception:
            if attempt == 29:
                raise
        time.sleep(1)
    else:
        raise ImportBlocked("Public resource metadata did not become available.")
    download_url = metadata_url + "/file"
    digest, size = hashlib.sha256(), 0
    with client.request("GET", download_url) as response:
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > entry["bytes"]:
                raise ImportBlocked("Public download exceeded original size.")
            digest.update(chunk)
    if size != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
        raise ImportBlocked("Public download differs from the original source file.")
    if resource.dataset_id != dataset.pk or dataset.organization_id != org.pk:
        raise ImportBlocked("Imported parent relationship mismatch.")
    return {"metadata_http": 200, "download_http": 200, "sha256_matches": True,
            "download_bytes": size, "relationships_match": True,
            "metadata_url": metadata_url, "download_url": download_url}


def verify_existing_import(report, manifest_path):
    """Read-only database/API checks; never resumes a failed import."""
    import ast
    import re
    from pathlib import Path
    import requests
    from django.conf import settings
    from django.contrib import admin
    from django.contrib.auth import get_user_model
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.test import RequestFactory
    from django.urls import reverse, resolve
    from mcod.organizations.models import Organization
    from mcod.datasets.models import Dataset
    from mcod.resources.models import Resource, ResourceFile
    from scripts.aed_import_models import Manifest
    manifest = Manifest(manifest_path)
    report["status"] = "partial_import_halted"
    report["verification_only"] = True
    files = []
    client = Client(10 * 1024 * 1024, 25 * 1024 * 1024)
    admin_checks = {}
    staff = get_user_model().objects.filter(is_active=True, is_staff=True).first()
    for kind, model in (("institution", Organization), ("dataset", Dataset), ("resource", Resource)):
        expected = {entry["local_id"] for key, entry in manifest.state["objects"].items()
                    if key.startswith(kind + ":") and entry.get("local_id")}
        if not staff or model not in admin.site._registry:
            raise ImportBlocked("Cannot verify the existing admin with current staff permissions.")
        path = reverse("admin:{}_{}_changelist".format(model._meta.app_label, model._meta.model_name))
        request = RequestFactory().get(path, secure=True, HTTP_HOST=urlsplit(settings.API_URL).netloc)
        request.resolver_match = resolve(path)
        request.user, request.session = staff, {}
        request._messages = FallbackStorage(request)
        response = admin.site._registry[model].changelist_view(request)
        response.render()
        actual = {obj.pk for obj in response.context_data["cl"].result_list}
        if response.status_code != 200 or not expected <= actual:
            raise ImportBlocked("Imported records are not visible in the original admin list.")
        admin_checks[kind] = {"status": 200, "visible_local_ids": sorted(expected),
                             "method": "Original admin view rendered in process with existing staff; no login/session created."}
    for key, entry in manifest.state["files"].items():
        owned = manifest.state["objects"]["resource:" + key]
        resource = Resource.objects.get(pk=owned["local_id"], uuid=owned["uuid"])
        file_obj = ResourceFile.objects.get(pk=entry["file_id"], resource=resource)
        if file_obj.file.name != entry["storage_name"]:
            raise ImportBlocked("File relationship or storage path mismatch.")
        content = manifest.client.download_as_bytes(entry["storage_name"])
        if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ImportBlocked("Stored original bytes do not match their recorded source hash.")
        count = count_records(content, entry["format"])
        if count != entry["records"]:
            raise ImportBlocked("Independent record recount differs from the initial count.")
        info = {"source_resource_id": key, "local_resource_id": resource.pk,
                "source_dataset_id": next(v["source_id"] for k, v in manifest.state["objects"].items()
                                          if k.startswith("dataset:") and v.get("local_id") == resource.dataset_id),
                "local_dataset_id": resource.dataset_id, "status": resource.status,
                "format": entry["format"], "bytes": len(content), "records": count,
                "sha256": entry["sha256"], "original_name": entry["original_name"],
                "storage_name": entry["storage_name"], "app_storage_bytes_verified": True,
                "validation": {"file": resource.file_tasks_last_status,
                               "link": resource.link_tasks_last_status,
                               "data": resource.data_tasks_last_status or "not_applicable"},
                "source_dates": {name: owned["source"]["attributes"].get(name)
                                 for name in ("created", "modified", "verified")},
                "local_dates": {name: str(getattr(resource, name))
                                for name in ("created", "modified", "verified")}}
        if resource.status == "published":
            info["api"] = verify_import(resource.dataset.organization, resource.dataset,
                                        resource, entry, settings.API_URL, client)
        else:
            client.trusted_origin = urlsplit(settings.API_URL).netloc
            statuses = []
            for suffix in ("", "/file"):
                try:
                    with client.request("GET", settings.API_URL.rstrip("/") + "/resources/" +
                                        str(resource.pk) + suffix) as response:
                        statuses.append(response.status_code)
                except requests.HTTPError as exc:
                    statuses.append(exc.response.status_code)
            if any(code not in (403, 404) for code in statuses):
                raise ImportBlocked("A draft resource leaked through the public API.")
            info["api"] = {"draft_metadata_status": statuses[0], "draft_file_status": statuses[1],
                           "draft_not_public": True}
        files.append(info)
    report["files"] = files
    report["datasets"] = []
    for key, entry in manifest.state["objects"].items():
        if key.startswith("dataset:"):
            dataset = Dataset.objects.get(pk=entry["local_id"], uuid=entry["uuid"])
            attrs = entry["source"]["attributes"]
            license_name = dict(Dataset.LICENSES)[dataset.license_chosen]
            if license_name != attrs["license_name"]:
                raise ImportBlocked("Imported source license changed.")
            report["datasets"].append({
                "source_id": entry["source_id"], "local_id": dataset.pk,
                "local_institution_id": dataset.organization_id, "title": dataset.title,
                "source_license": attrs["license_name"], "local_license": str(license_name),
                "license_conditions_in_manifest": {key: value for key, value in attrs.items()
                                                   if key.startswith("license_condition")},
                "status": dataset.status,
            })
    report["verification"]["admin"] = admin_checks
    report["verification"]["signed_in_browser_ui"] = "not_verified; original admin rendered in an in-process test"
    report["verification"]["all_stored_original_checksums_match"] = True
    report["verification"]["public_download_checksums_match"] = all(
        item["api"].get("sha256_matches") for item in files if item["status"] == "published")
    report["counts"].update({
        "stored_original_files": len(files), "stored_original_bytes": sum(i["bytes"] for i in files),
        "stored_original_gb": sum(i["bytes"] for i in files) / 1e9,
        "published_resources": sum(i["status"] == "published" for i in files),
        "draft_resources": sum(i["status"] == "draft" for i in files),
        "aed_rows_counted": sum(i["records"] for i in files if i["records"] is not None),
        "downloaded_files_this_run": 0, "downloaded_bytes_this_run": 0,
    })
    logs = sorted(Path("reports/aed-import-runs").glob("*.json"))
    runs = [json.loads(path.read_text()) for path in logs]
    pilot_log = Path("/tmp/aed-pilot-run.log")
    if pilot_log.exists():
        runs += [json.loads(line) for line in pilot_log.read_text().splitlines()
                 if line.startswith('{"status":')]
    report["counts"]["source_file_transfers_recorded"] = sum(
        run["counts"]["downloaded_files_this_run"] for run in runs)
    report["counts"]["source_bytes_transferred_recorded"] = sum(
        run["counts"]["downloaded_bytes_this_run"] for run in runs)
    idem = json.loads(Path("reports/aed-pilot-idempotency.json").read_text())
    report["verification"]["pilot_idempotency"] = {
        "created": idem["counts"]["created_this_run"],
        "source_files_downloaded": idem["counts"]["downloaded_files_this_run"],
        "status": idem["status"],
    }
    errors_log = Path("/tmp/aed-przemysl-resume.log")
    match = re.search(r"process_resource_file_data_task raised (\[.*\]) - transaction commits",
                      errors_log.read_text() if errors_log.exists() else "")
    if match:
        report["original_data_validation_errors"] = ast.literal_eval(match.group(1))
    report["source_timestamp_policy"] = (
        "Exact source timestamps are retained in the durable manifest. MCOD assigns its own "
        "local modified/verified timestamps during publication and validation; these were not forcibly overwritten.")
    report["remaining_sources"] = [
        {"dataset": "4581", "resource": "62095", "reason": "Original integer-column validation failed; kept draft."},
        {"dataset": "4581", "resource": "62424", "reason": "Not attempted after the validation failure."},
        {"dataset": "4955", "resources": ["68353", "68355"], "reason": "Not attempted after the validation failure."},
        {"dataset": "39512", "resource": "2512040", "reason": "Unknown file size; file_url points to an external catalogue, not a verified downloadable JSON file."},
    ]
    return report
