"""
Script: load_data_opensearch.py
Deskripsi: Memuat data Rumah Sakit Sehat Selalu ke dalam OpenSearch
           dengan format yang dioptimalkan untuk pencarian semantik (RAG/QA System)

Jalankan dengan: python load_data_opensearch.py
"""

import json
import os
from opensearchpy import OpenSearch, helpers
from datetime import datetime

# ============================================================
# KONFIGURASI OPENSEARCH
# ============================================================
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", 9200))
OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", "admin")
OPENSEARCH_PASS = os.getenv("OPENSEARCH_PASS", "admin")

client = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
    http_auth=(OPENSEARCH_USER, OPENSEARCH_PASS),
    use_ssl=False,
    verify_certs=False,
    ssl_show_warn=False,
)

# ============================================================
# DEFINISI INDEX DAN MAPPING
# ============================================================

INDEX_NAME = "rumah_sakit"

INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "analysis": {
            "analyzer": {
                "indonesian_analyzer": {
                    "type": "standard",
                    "stopwords": "_indonesian_"
                }
            }
        }
    },
    "mappings": {
        "properties": {
            # === Identitas Dokumen ===
            "doc_type": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            "content": {
                "type": "text",
                "analyzer": "indonesian_analyzer"
            },

            # === Field Dokter ===
            "doctor_id": {"type": "keyword"},
            "nama_dokter": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword"}}
            },
            "spesialisasi": {"type": "keyword"},
            "no_str": {"type": "keyword"},
            "telepon_dokter": {"type": "keyword"},

            # === Field Pasien ===
            "pasien_id": {"type": "keyword"},
            "nama_pasien": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword"}}
            },
            "tanggal_lahir": {"type": "date"},
            "jenis_kelamin": {"type": "keyword"},
            "alamat": {"type": "text"},
            "telepon_pasien": {"type": "keyword"},
            "golongan_darah": {"type": "keyword"},
            "nok": {"type": "text"},

            # === Field Registrasi ===
            "register_id": {"type": "keyword"},
            "tanggal_kunjungan": {"type": "date"},
            "keluhan": {"type": "text", "analyzer": "indonesian_analyzer"},
            "poli": {"type": "keyword"},
            "status_kunjungan": {"type": "keyword"},

            # === Field Tagihan ===
            "bills_id": {"type": "keyword"},
            "total_bill": {"type": "long"},
            "status_bayar": {"type": "boolean"},
            "tanggal_tagihan": {"type": "date"},
            "metode_bayar": {"type": "keyword"},
            "biaya_dokter": {"type": "long"},
            "biaya_obat": {"type": "long"},
            "biaya_tindakan": {"type": "long"},
            "biaya_kamar": {"type": "long"},
        }
    }
}

# ============================================================
# FUNGSI HELPER
# ============================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def create_index():
    """Buat index OpenSearch jika belum ada"""
    if client.indices.exists(index=INDEX_NAME):
        print(f"[INFO] Index '{INDEX_NAME}' sudah ada. Menghapus dan membuat ulang...")
        client.indices.delete(index=INDEX_NAME)
    client.indices.create(index=INDEX_NAME, body=INDEX_MAPPING)
    print(f"[OK] Index '{INDEX_NAME}' berhasil dibuat.")

def bulk_index(docs):
    """Indeks dokumen secara batch"""
    success, failed = helpers.bulk(client, docs, raise_on_error=False)
    print(f"[OK] Berhasil: {success} dokumen | Gagal: {len(failed)} dokumen")

# ============================================================
# TRANSFORMASI DATA
# ============================================================

def transform_dokter(dokter_list, registrasi_list):
    """Transform data dokter + hitung statistik kunjungan"""
    reg_by_doc = {}
    for r in registrasi_list:
        did = r["doctor_id"]
        reg_by_doc.setdefault(did, []).append(r)

    docs = []
    for d in dokter_list:
        did = d["doctor_id"]
        regs = reg_by_doc.get(did, [])
        poli_list = list(set(r["poli"] for r in regs))

        content = (
            f"Dokter {d['nama']} adalah spesialis {d['spesialisasi']} "
            f"dengan nomor STR {d['no_str']}. "
            f"Dapat dihubungi di nomor {d['no_telepon']}. "
            f"Telah menangani {len(regs)} kunjungan pasien. "
            f"Poli yang ditangani: {', '.join(poli_list) if poli_list else d['spesialisasi']}."
        )

        docs.append({
            "_index": INDEX_NAME,
            "_id": f"dokter_{did}",
            "_source": {
                "doc_type": "dokter",
                "doc_id": did,
                "content": content,
                "doctor_id": did,
                "nama_dokter": d["nama"],
                "spesialisasi": d["spesialisasi"],
                "no_str": d["no_str"],
                "telepon_dokter": d["no_telepon"],
                "total_kunjungan": len(regs),
            }
        })
    print(f"[INFO] Menyiapkan {len(docs)} dokumen dokter...")
    return docs


def transform_pasien(pasien_list, registrasi_list, tagihan_list):
    """Transform data pasien + ringkasan riwayat"""
    reg_by_pasien = {}
    for r in registrasi_list:
        pid = r["pasien_id"]
        reg_by_pasien.setdefault(pid, []).append(r)

    tagihan_by_reg = {t["register_id"]: t for t in tagihan_list}

    docs = []
    for p in pasien_list:
        pid = p["pasien_id"]
        regs = reg_by_pasien.get(pid, [])
        total_tagihan = sum(
            tagihan_by_reg[r["register_id"]]["total_bill"]
            for r in regs if r["register_id"] in tagihan_by_reg
        )
        keluhan_list = [r["keluhan"] for r in regs]

        lahir = p.get("tanggal_lahir", "")
        try:
            thn = int(lahir[:4])
            usia = datetime.now().year - thn
        except:
            usia = 0

        content = (
            f"Pasien {p['nama']} lahir pada {lahir} (usia sekitar {usia} tahun), "
            f"jenis kelamin {p['jenis_kelamin']}, golongan darah {p['golongan_darah']}. "
            f"Alamat: {p['alamat']}. "
            f"Kontak darurat: {p['nok']} ({p.get('kontak_nok', '-')}). "
            f"Telah melakukan {len(regs)} kunjungan. "
            f"Keluhan pernah dialami: {'; '.join(set(keluhan_list))[:300]}. "
            f"Total tagihan seluruh kunjungan: Rp {total_tagihan:,}."
        )

        docs.append({
            "_index": INDEX_NAME,
            "_id": f"pasien_{pid}",
            "_source": {
                "doc_type": "pasien",
                "doc_id": pid,
                "content": content,
                "pasien_id": pid,
                "nama_pasien": p["nama"],
                "tanggal_lahir": lahir,
                "jenis_kelamin": p["jenis_kelamin"],
                "alamat": p["alamat"],
                "telepon_pasien": p.get("no_telepon", ""),
                "golongan_darah": p["golongan_darah"],
                "nok": p["nok"],
                "total_kunjungan": len(regs),
                "total_tagihan_semua": total_tagihan,
            }
        })
    print(f"[INFO] Menyiapkan {len(docs)} dokumen pasien...")
    return docs


def transform_registrasi(registrasi_list, pasien_dict, dokter_dict, tagihan_by_reg):
    """Transform data registrasi + join dengan pasien, dokter, dan tagihan"""
    docs = []
    for r in registrasi_list:
        rid = r["register_id"]
        pasien = pasien_dict.get(r["pasien_id"], {})
        dokter = dokter_dict.get(r["doctor_id"], {})
        tagihan = tagihan_by_reg.get(rid, {})

        status_bayar_str = "lunas" if tagihan.get("status") else "belum lunas"
        total = tagihan.get("total_bill", 0)

        content = (
            f"Registrasi {rid}: Pasien {pasien.get('nama', r['pasien_id'])} "
            f"berkunjung ke poli {r['poli']} pada {r['date'][:10]} "
            f"dengan status {r['status_kunjungan']}. "
            f"Ditangani oleh Dr. {dokter.get('nama', r['doctor_id'])} spesialis {dokter.get('spesialisasi', '')}. "
            f"Keluhan: {r['keluhan']}. "
            f"Tagihan: Rp {total:,} ({status_bayar_str}) "
            f"melalui metode {tagihan.get('metode_bayar', '-')}."
        )

        doc = {
            "_index": INDEX_NAME,
            "_id": f"reg_{rid}",
            "_source": {
                "doc_type": "registrasi",
                "doc_id": rid,
                "content": content,
                "register_id": rid,
                "pasien_id": r["pasien_id"],
                "doctor_id": r["doctor_id"],
                "nama_pasien": pasien.get("nama", ""),
                "nama_dokter": dokter.get("nama", ""),
                "spesialisasi": dokter.get("spesialisasi", ""),
                "tanggal_kunjungan": r["date"],
                "keluhan": r["keluhan"],
                "poli": r["poli"],
                "status_kunjungan": r["status_kunjungan"],
            }
        }

        # Tambahkan data tagihan jika ada
        if tagihan:
            rincian = tagihan.get("rincian", {})
            doc["_source"].update({
                "bills_id": tagihan.get("bills_id", ""),
                "total_bill": total,
                "status_bayar": tagihan.get("status", False),
                "tanggal_tagihan": tagihan.get("bills_date", ""),
                "metode_bayar": tagihan.get("metode_bayar", ""),
                "biaya_dokter": rincian.get("biaya_dokter", 0),
                "biaya_obat": rincian.get("biaya_obat", 0),
                "biaya_tindakan": rincian.get("biaya_tindakan", 0),
                "biaya_kamar": rincian.get("biaya_kamar", 0),
            })

        docs.append(doc)

    print(f"[INFO] Menyiapkan {len(docs)} dokumen registrasi...")
    return docs


def transform_tagihan(tagihan_list, registrasi_dict, pasien_dict, dokter_dict):
    """Transform data tagihan sebagai dokumen mandiri untuk analitik"""
    docs = []
    for t in tagihan_list:
        rid = t["register_id"]
        reg = registrasi_dict.get(rid, {})
        pasien = pasien_dict.get(reg.get("pasien_id", ""), {})
        dokter = dokter_dict.get(reg.get("doctor_id", ""), {})
        rincian = t.get("rincian", {})

        status_str = "lunas" if t["status"] else "belum lunas"
        content = (
            f"Tagihan {t['bills_id']} untuk registrasi {rid} "
            f"atas nama {pasien.get('nama', 'pasien tidak diketahui')} "
            f"tanggal {t['bills_date'][:10]}. "
            f"Total tagihan Rp {t['total_bill']:,} dengan status {status_str}. "
            f"Pembayaran via {t['metode_bayar']}. "
            f"Rincian: biaya dokter Rp {rincian.get('biaya_dokter',0):,}, "
            f"biaya obat Rp {rincian.get('biaya_obat',0):,}, "
            f"biaya tindakan Rp {rincian.get('biaya_tindakan',0):,}, "
            f"biaya kamar Rp {rincian.get('biaya_kamar',0):,}."
        )

        docs.append({
            "_index": INDEX_NAME,
            "_id": f"tagihan_{t['bills_id']}",
            "_source": {
                "doc_type": "tagihan",
                "doc_id": t["bills_id"],
                "content": content,
                "bills_id": t["bills_id"],
                "register_id": rid,
                "pasien_id": reg.get("pasien_id", ""),
                "nama_pasien": pasien.get("nama", ""),
                "doctor_id": reg.get("doctor_id", ""),
                "nama_dokter": dokter.get("nama", ""),
                "total_bill": t["total_bill"],
                "status_bayar": t["status"],
                "tanggal_tagihan": t["bills_date"],
                "metode_bayar": t["metode_bayar"],
                "biaya_dokter": rincian.get("biaya_dokter", 0),
                "biaya_obat": rincian.get("biaya_obat", 0),
                "biaya_tindakan": rincian.get("biaya_tindakan", 0),
                "biaya_kamar": rincian.get("biaya_kamar", 0),
            }
        })

    print(f"[INFO] Menyiapkan {len(docs)} dokumen tagihan...")
    return docs


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("LOAD DATA RUMAH SAKIT SEHAT SELALU KE OPENSEARCH")
    print("=" * 60)

    # Cek koneksi
    info = client.info()
    print(f"[OK] Terhubung ke OpenSearch versi {info['version']['number']}")

    # Load raw data
    print("\n[STEP 1] Membaca file JSON...")
    DATA_DIR = os.getenv("DATA_DIR", "./data")
    dokter_data     = load_json(os.path.join(DATA_DIR, "rumah_sakit_dokter.json"))
    pasien_data     = load_json(os.path.join(DATA_DIR, "rumah_sakit_pasien.json"))
    registrasi_data = load_json(os.path.join(DATA_DIR, "rumah_sakit_registrasi.json"))
    tagihan_data    = load_json(os.path.join(DATA_DIR, "rumah_sakit_tagihan.json"))

    print(f"  Dokter    : {len(dokter_data)} records")
    print(f"  Pasien    : {len(pasien_data)} records")
    print(f"  Registrasi: {len(registrasi_data)} records")
    print(f"  Tagihan   : {len(tagihan_data)} records")

    # Buat lookup dict
    pasien_dict   = {p["pasien_id"]: p for p in pasien_data}
    dokter_dict   = {d["doctor_id"]: d for d in dokter_data}
    reg_dict      = {r["register_id"]: r for r in registrasi_data}
    tagihan_by_reg= {t["register_id"]: t for t in tagihan_data}

    # Buat index
    print("\n[STEP 2] Membuat index OpenSearch...")
    create_index()

    # Transform dan load data
    print("\n[STEP 3] Mentransformasi dan mengindeks data...")

    all_docs = []
    all_docs += transform_dokter(dokter_data, registrasi_data)
    all_docs += transform_pasien(pasien_data, registrasi_data, tagihan_data)
    all_docs += transform_registrasi(registrasi_data, pasien_dict, dokter_dict, tagihan_by_reg)
    all_docs += transform_tagihan(tagihan_data, reg_dict, pasien_dict, dokter_dict)

    print(f"\n[STEP 4] Mengindeks {len(all_docs)} dokumen ke OpenSearch...")
    bulk_index(all_docs)

    # Verifikasi
    client.indices.refresh(index=INDEX_NAME)
    count = client.count(index=INDEX_NAME)["count"]
    print(f"\n[OK] Total dokumen terindeks: {count}")
    print("\n[SELESAI] Data berhasil dimuat ke OpenSearch!")


if __name__ == "__main__":
    main()
