"""
denormalize.py
--------------
Join tagihan + registrasi + dokter + pasien into a single flat JSON
for OpenSearch indexing.

Input  : ./data/raw/*.json 
Output : ./data/processed/tagihan_denormalized.json

Run from project root:
    python scripts/denormalize.py
"""

import json
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
RAW_DIR = os.path.join("data", "raw")
PROCESSED_DIR = os.path.join("data", "processed")
os.makedirs(PROCESSED_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_json(filename: str) -> list[dict]:
    path = os.path.join(RAW_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"  Loaded {len(data):>5} records  <-  {filename}")
    return data


def build_lookup(records: list[dict], key_field: str) -> dict:
    """Build a dict keyed by key_field for O(1) lookups."""
    lookup = {}
    for rec in records:
        k = rec.get(key_field)
        if k:
            lookup[k] = rec
    return lookup


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n[1/4] Loading raw JSON files ...")
    tagihan    = load_json("rumah_sakit_tagihan.json")
    registrasi = load_json("rumah_sakit_registrasi.json")
    dokter     = load_json("rumah_sakit_dokter.json")
    pasien     = load_json("rumah_sakit_pasien.json")

    print("\n[2/4] Building lookup tables ...")
    reg_lookup    = build_lookup(registrasi, "register_id")
    dokter_lookup = build_lookup(dokter,     "doctor_id")
    pasien_lookup = build_lookup(pasien,     "pasien_id")

    print(f"  registrasi lookup : {len(reg_lookup)} entries")
    print(f"  dokter     lookup : {len(dokter_lookup)} entries")
    print(f"  pasien     lookup : {len(pasien_lookup)} entries")

    print("\n[3/4] Joining records ...")
    results = []
    stats = {
        "total":             len(tagihan),
        "ok":                0,
        "missing_registrasi": 0,
        "missing_dokter":    0,
        "missing_pasien":    0,
    }

    for t in tagihan:
        register_id = t.get("register_id")
        reg = reg_lookup.get(register_id)

        if reg is None:
            stats["missing_registrasi"] += 1
            continue

        doctor_id = reg.get("doctor_id")
        dok = dokter_lookup.get(doctor_id)
        if dok is None:
            stats["missing_dokter"] += 1

        pasien_id = reg.get("pasien_id")
        pas = pasien_lookup.get(pasien_id)
        if pas is None:
            stats["missing_pasien"] += 1

        rincian = t.get("rincian", {})

        # Parse bills_date to a clean ISO date string
        bills_date_raw = t.get("bills_date", "")
        try:
            bills_date = datetime.fromisoformat(
                bills_date_raw.replace("Z", "+00:00")
            ).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            bills_date = bills_date_raw

        reg_date_raw = reg.get("date", "")
        try:
            reg_date = datetime.fromisoformat(
                reg_date_raw.replace("Z", "+00:00")
            ).strftime("%Y-%m-%dT%H:%M:%S")
        except Exception:
            reg_date = reg_date_raw

        doc = {
            # --- Tagihan ---
            "bills_id":         t.get("bills_id"),
            "register_id":      register_id,
            "total_bill":       t.get("total_bill"),
            "status_bayar":     t.get("status"),        # bool: True = lunas
            "metode_bayar":     t.get("metode_bayar"),
            "bills_date":       bills_date,
            # Rincian biaya
            "biaya_dokter":     rincian.get("biaya_dokter",   0),
            "biaya_obat":       rincian.get("biaya_obat",     0),
            "biaya_tindakan":   rincian.get("biaya_tindakan", 0),
            "biaya_kamar":      rincian.get("biaya_kamar",    0),
            # --- Registrasi ---
            "reg_date":         reg_date,
            "keluhan":          reg.get("keluhan"),
            "poli":             reg.get("poli"),
            "status_kunjungan": reg.get("status_kunjungan"),
            # --- Dokter ---
            "doctor_id":        doctor_id,
            "nama_dokter":      dok.get("nama")         if dok else None,
            "spesialisasi":     dok.get("spesialisasi") if dok else None,
            # --- Pasien ---
            "pasien_id":        pasien_id,
            "nama_pasien":      pas.get("nama")          if pas else None,
            "jenis_kelamin":    pas.get("jenis_kelamin") if pas else None,
            "golongan_darah":   pas.get("golongan_darah") if pas else None,
        }

        results.append(doc)
        stats["ok"] += 1

    print(f"\n  Join results:")
    print(f"    Total tagihan        : {stats['total']}")
    print(f"    Successfully joined  : {stats['ok']}")
    print(f"    Missing registrasi   : {stats['missing_registrasi']}")
    print(f"    Missing dokter       : {stats['missing_dokter']}")
    print(f"    Missing pasien       : {stats['missing_pasien']}")

    print("\n[4/4] Writing output ...")
    out_path = os.path.join(PROCESSED_DIR, "tagihan_denormalized.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"  Done -> {out_path}  ({len(results)} documents)\n")


if __name__ == "__main__":
    main()