import os
import re
import json
import time
import urllib.request
import subprocess

GRAFANA_DS_URL = "https://kylash.grafana.net/api/ds/query"
INFINITY_UID = "eform1zhhjjswb"
BASE_N8N_URL = "https://n8n-fggh.onrender.com"
TARGET_DIR = "/Users/jayashreesundarasamy/kylasam/PycharmProjects/deploy_services_render.com/workflows"

def get_grafana_token():
    token = os.getenv("GRAFANA_TOKEN")
    if token:
        return token
    try:
        out = subprocess.check_output(
            ["gcloud", "secrets", "versions", "access", "latest", "--secret=GRAFANA_TOKEN", "--project=wealthyo"],
            stderr=subprocess.DEVNULL
        )
        return out.decode().strip()
    except Exception as e:
        print(f"Warning: Could not fetch GRAFANA_TOKEN from Secret Manager: {e}")
        return ""

GRAFANA_TOKEN = get_grafana_token()

def call_infinity_api(url_path):
    query_payload = {
        "queries": [{
            "refId": "A",
            "datasource": {"type": "yesoreyeram-infinity-datasource", "uid": INFINITY_UID},
            "type": "json",
            "source": "url",
            "url": f"{BASE_N8N_URL}{url_path}",
            "url_options": {"method": "GET"}
        }]
    }
    req = urllib.request.Request(
        GRAFANA_DS_URL,
        data=json.dumps(query_payload).encode(),
        headers={
            "Authorization": f"Bearer {GRAFANA_TOKEN}",
            "Content-Type": "application/json"
        }
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def get_all_workflows_summary():
    res = call_infinity_api("/api/v1/workflows")
    raw_data = res["results"]["A"]["frames"][0]["data"]["values"][0][0]
    return json.loads(raw_data)

def get_workflow_detail(wf_id):
    res = call_infinity_api(f"/api/v1/workflows/{wf_id}")
    frame = res["results"]["A"]["frames"][0]
    fields = [f["name"] for f in frame["schema"]["fields"]]
    data = {}
    for name, val in zip(fields, frame["data"]["values"]):
        v = val[0]
        if isinstance(v, str) and (v.startswith("{") or v.startswith("[")):
            try:
                v = json.loads(v)
            except Exception:
                pass
        data[name] = v
    return data

def sanitize_filename(name):
    # Remove characters illegal in filenames across OS
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return clean

def sanitize_secrets_in_json(obj_str):
    # Replace sensitive API keys with environment variable expressions or placeholders
    # 1. Resend API Keys (re_...)
    obj_str = re.sub(r're_[A-Za-z0-9_-]{20,}', 'YOUR_RESEND_API_KEY', obj_str)
    # 2. ClickUp Personal Tokens (pk_...)
    obj_str = re.sub(r'pk_[A-Za-z0-9_]{30,}', 'YOUR_CLICKUP_API_TOKEN', obj_str)
    # 3. Meta Access Tokens (EAA...)
    obj_str = re.sub(r'EAA[A-Za-z0-9_-]{100,}', 'YOUR_META_ACCESS_TOKEN', obj_str)
    # 4. Buffer Tokens (Bearer 6dB...)
    obj_str = re.sub(r'Bearer\s+6dB2NfDZRxXoXKO-[A-Za-z0-9_-]+', 'Bearer YOUR_BUFFER_ACCESS_TOKEN', obj_str)
    # 5. Grafana Service Account Tokens (glsa_...)
    obj_str = re.sub(r'glsa_[A-Za-z0-9_-]{25,}', 'YOUR_GRAFANA_TOKEN', obj_str)
    # 6. Google API Keys (AIzaSy...)
    obj_str = re.sub(r'AIzaSy[A-Za-z0-9_-]{30,}', 'YOUR_GOOGLE_API_KEY', obj_str)
    return obj_str

def main():
    os.makedirs(TARGET_DIR, exist_ok=True)
    workflows = get_all_workflows_summary()
    print(f"Discovered {len(workflows)} workflows on n8n.")

    name_counts = {}
    for wf in workflows:
        base = sanitize_filename(wf["name"])
        name_counts[base] = name_counts.get(base, 0) + 1

    synced_items = []

    for idx, wf_summary in enumerate(workflows, 1):
        wf_id = wf_summary["id"]
        wf_name = wf_summary["name"]
        print(f"[{idx}/{len(workflows)}] Fetching: {wf_name} ({wf_id})...")

        try:
            detail = get_workflow_detail(wf_id)
        except Exception as e:
            print(f"  Error fetching {wf_id}: {e}")
            continue

        base_clean = sanitize_filename(wf_name)
        if name_counts[base_clean] > 1:
            filename = f"{base_clean}_{wf_id}.json"
        else:
            filename = f"{base_clean}.json"

        target_file = os.path.join(TARGET_DIR, filename)

        export_payload = {
            "name": detail.get("name"),
            "nodes": detail.get("nodes", []),
            "connections": detail.get("connections", {}),
            "active": detail.get("active", False),
            "settings": detail.get("settings", {}),
            "versionId": detail.get("versionId"),
            "id": detail.get("id"),
            "meta": detail.get("meta", {}),
            "tags": detail.get("tags", [])
        }

        # Convert to JSON string and sanitize secrets
        raw_json_str = json.dumps(export_payload, indent=2, ensure_ascii=False)
        sanitized_json_str = sanitize_secrets_in_json(raw_json_str)

        with open(target_file, "w", encoding="utf-8") as f:
            f.write(sanitized_json_str)
            f.write("\n")

        print(f"  Saved -> {filename}")

        if wf_id == "dutvD7ovTB4Fv9xX":
            for legacy in ["n8n-centralized-email-workflow.json", "wealthyo-numeric-valuation-workflow.json"]:
                legacy_path = os.path.join(TARGET_DIR, legacy)
                with open(legacy_path, "w", encoding="utf-8") as f:
                    f.write(sanitized_json_str)
                    f.write("\n")
                print(f"  Synced legacy file -> {legacy}")

        synced_items.append({
            "id": wf_id,
            "name": wf_name,
            "active": detail.get("active", False),
            "nodes_count": len(detail.get("nodes", [])),
            "filename": filename,
            "updated_at": detail.get("updatedAt", "")
        })

        time.sleep(0.3)

    readme_path = os.path.join(TARGET_DIR, "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("# ⚡ Wealthyo & Homelyo Production n8n Workflows\n\n")
        f.write("This directory contains the automated sync of all production workflows from `https://n8n-fggh.onrender.com`.\n\n")
        f.write(f"Total Workflows: **{len(synced_items)}**\n\n")
        f.write("| ID | Workflow Name | Active | Nodes | Workflow File |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for item in sorted(synced_items, key=lambda x: x["name"].lower()):
            active_badge = "🟢 `Active`" if item["active"] else "⚪ `Inactive`"
            f.write(f"| `{item['id']}` | **{item['name']}** | {active_badge} | {item['nodes_count']} | [`{item['filename']}`](./{item['filename']}) |\n")
        f.write("\n---\n*Last synced via automated sync tool.*\n")

    print(f"\nSuccessfully synced {len(synced_items)} workflows and generated README.md index!")

if __name__ == "__main__":
    main()
