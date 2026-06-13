"""
opensearch_client.py
--------------------
Handles all OpenSearch connections and query execution.
Provides aggregation helpers for biaya operasional analytics.
"""

import os
from opensearchpy import OpenSearch

INDEX = "tagihan_operasional"

_client: OpenSearch | None = None


def get_client() -> OpenSearch:
    global _client
    if _client is None:
        host = os.getenv("OPENSEARCH_HOST", "localhost")
        port = int(os.getenv("OPENSEARCH_PORT", 9200))
        _client = OpenSearch(
            hosts=[{"host": host, "port": port}],
            use_ssl=False,
            verify_certs=False,
            http_compress=True,
        )
    return _client


# ---------------------------------------------------------------------------
# Generic search
# ---------------------------------------------------------------------------

def run_query(body: dict) -> dict:
    client = get_client()
    return client.search(index=INDEX, body=body)


# ---------------------------------------------------------------------------
# Predefined aggregation queries
# ---------------------------------------------------------------------------

def total_biaya_per_komponen(filters: dict | None = None) -> dict:
    """Sum biaya_dokter, biaya_obat, biaya_tindakan, biaya_kamar."""
    query = _build_filter(filters)
    body = {
        "size": 0,
        "query": query,
        "aggs": {
            "total_biaya_dokter":   {"sum": {"field": "biaya_dokter"}},
            "total_biaya_obat":     {"sum": {"field": "biaya_obat"}},
            "total_biaya_tindakan": {"sum": {"field": "biaya_tindakan"}},
            "total_biaya_kamar":    {"sum": {"field": "biaya_kamar"}},
            "total_keseluruhan":    {"sum": {"field": "total_bill"}},
        },
    }
    res = run_query(body)
    return _extract_aggs(res)


def rata_rata_biaya_per_komponen(filters: dict | None = None) -> dict:
    """Average biaya per komponen."""
    query = _build_filter(filters)
    body = {
        "size": 0,
        "query": query,
        "aggs": {
            "avg_biaya_dokter":   {"avg": {"field": "biaya_dokter"}},
            "avg_biaya_obat":     {"avg": {"field": "biaya_obat"}},
            "avg_biaya_tindakan": {"avg": {"field": "biaya_tindakan"}},
            "avg_biaya_kamar":    {"avg": {"field": "biaya_kamar"}},
            "avg_total_bill":     {"avg": {"field": "total_bill"}},
        },
    }
    res = run_query(body)
    return _extract_aggs(res)


def biaya_per_poli(filters: dict | None = None) -> dict:
    """Total biaya grouped by poli."""
    query = _build_filter(filters)
    body = {
        "size": 0,
        "query": query,
        "aggs": {
            "per_poli": {
                "terms": {"field": "poli", "size": 20},
                "aggs": {
                    "total_bill":     {"sum": {"field": "total_bill"}},
                    "avg_bill":       {"avg": {"field": "total_bill"}},
                    "total_obat":     {"sum": {"field": "biaya_obat"}},
                    "total_tindakan": {"sum": {"field": "biaya_tindakan"}},
                },
            }
        },
    }
    res = run_query(body)
    buckets = res["aggregations"]["per_poli"]["buckets"]
    return {
        b["key"]: {
            "jumlah_kunjungan": b["doc_count"],
            "total_bill":       b["total_bill"]["value"],
            "avg_bill":         b["avg_bill"]["value"],
            "total_obat":       b["total_obat"]["value"],
            "total_tindakan":   b["total_tindakan"]["value"],
        }
        for b in buckets
    }


def biaya_per_spesialisasi(filters: dict | None = None) -> dict:
    """Total biaya grouped by spesialisasi dokter."""
    query = _build_filter(filters)
    body = {
        "size": 0,
        "query": query,
        "aggs": {
            "per_spesialisasi": {
                "terms": {"field": "spesialisasi", "size": 20},
                "aggs": {
                    "total_bill":   {"sum": {"field": "total_bill"}},
                    "avg_bill":     {"avg": {"field": "total_bill"}},
                    "total_dokter": {"sum": {"field": "biaya_dokter"}},
                },
            }
        },
    }
    res = run_query(body)
    buckets = res["aggregations"]["per_spesialisasi"]["buckets"]
    return {
        b["key"]: {
            "jumlah_kasus":   b["doc_count"],
            "total_bill":     b["total_bill"]["value"],
            "avg_bill":       b["avg_bill"]["value"],
            "total_dokter":   b["total_dokter"]["value"],
        }
        for b in buckets
    }


def biaya_per_bulan(filters: dict | None = None) -> dict:
    """Total biaya grouped by month (from bills_date)."""
    query = _build_filter(filters)
    body = {
        "size": 0,
        "query": query,
        "aggs": {
            "per_bulan": {
                "date_histogram": {
                    "field":             "bills_date",
                    "calendar_interval": "month",
                    "format":            "yyyy-MM",
                },
                "aggs": {
                    "total_bill":     {"sum": {"field": "total_bill"}},
                    "total_obat":     {"sum": {"field": "biaya_obat"}},
                    "total_tindakan": {"sum": {"field": "biaya_tindakan"}},
                    "total_kamar":    {"sum": {"field": "biaya_kamar"}},
                    "total_dokter":   {"sum": {"field": "biaya_dokter"}},
                },
            }
        },
    }
    res = run_query(body)
    buckets = res["aggregations"]["per_bulan"]["buckets"]
    return {
        b["key_as_string"]: {
            "jumlah_tagihan": b["doc_count"],
            "total_bill":     b["total_bill"]["value"],
            "total_obat":     b["total_obat"]["value"],
            "total_tindakan": b["total_tindakan"]["value"],
            "total_kamar":    b["total_kamar"]["value"],
            "total_dokter":   b["total_dokter"]["value"],
        }
        for b in buckets
        if b["doc_count"] > 0
    }


def biaya_per_status_kunjungan(filters: dict | None = None) -> dict:
    """Total biaya grouped by status kunjungan (rawat inap, jalan, darurat)."""
    query = _build_filter(filters)
    body = {
        "size": 0,
        "query": query,
        "aggs": {
            "per_status": {
                "terms": {"field": "status_kunjungan", "size": 10},
                "aggs": {
                    "total_bill": {"sum": {"field": "total_bill"}},
                    "avg_bill":   {"avg": {"field": "total_bill"}},
                },
            }
        },
    }
    res = run_query(body)
    buckets = res["aggregations"]["per_status"]["buckets"]
    return {
        b["key"]: {
            "jumlah_kunjungan": b["doc_count"],
            "total_bill":       b["total_bill"]["value"],
            "avg_bill":         b["avg_bill"]["value"],
        }
        for b in buckets
    }


def metode_bayar_distribution(filters: dict | None = None) -> dict:
    """Distribution of payment methods."""
    query = _build_filter(filters)
    body = {
        "size": 0,
        "query": query,
        "aggs": {
            "per_metode": {
                "terms": {"field": "metode_bayar", "size": 10},
                "aggs": {
                    "total_bill": {"sum": {"field": "total_bill"}},
                },
            }
        },
    }
    res = run_query(body)
    buckets = res["aggregations"]["per_metode"]["buckets"]
    return {
        b["key"]: {
            "jumlah":     b["doc_count"],
            "total_bill": b["total_bill"]["value"],
        }
        for b in buckets
    }


def summary_stats(filters: dict | None = None) -> dict:
    """Overall summary: count, total, avg, min, max bill."""
    query = _build_filter(filters)
    body = {
        "size": 0,
        "query": query,
        "aggs": {
            "stats_bill": {"extended_stats": {"field": "total_bill"}},
            "total_obat": {"sum": {"field": "biaya_obat"}},
            "total_tindakan": {"sum": {"field": "biaya_tindakan"}},
            "total_kamar": {"sum": {"field": "biaya_kamar"}},
            "total_dokter": {"sum": {"field": "biaya_dokter"}},
        },
    }
    res = run_query(body)
    aggs = res["aggregations"]
    stats = aggs["stats_bill"]
    return {
        "jumlah_tagihan": stats["count"],
        "total_bill":     stats["sum"],
        "avg_bill":       stats["avg"],
        "min_bill":       stats["min"],
        "max_bill":       stats["max"],
        "total_obat":     aggs["total_obat"]["value"],
        "total_tindakan": aggs["total_tindakan"]["value"],
        "total_kamar":    aggs["total_kamar"]["value"],
        "total_dokter":   aggs["total_dokter"]["value"],
    }


def get_database_stats() -> dict:
    """Get unique counts of doctor, patient, registration, and tagihan."""
    body = {
        "size": 0,
        "aggs": {
            "dokter_count": {"cardinality": {"field": "doctor_id"}},
            "pasien_count": {"cardinality": {"field": "pasien_id"}},
            "register_count": {"cardinality": {"field": "register_id"}},
            "tagihan_count": {"value_count": {"field": "bills_id"}},
        }
    }
    res = run_query(body)
    aggs = res["aggregations"]
    return {
        "dokter": aggs["dokter_count"]["value"],
        "pasien": aggs["pasien_count"]["value"],
        "registrasi": aggs["register_count"]["value"],
        "tagihan": aggs["tagihan_count"]["value"],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_filter_value(field: str, val: str) -> str:
    if not isinstance(val, str):
        return val

    val = val.strip()

    if field == "status_kunjungan":
        return val.lower()

    if field == "metode_bayar":
        if val.upper() == "BPJS":
            return "BPJS"
        return val.title()

    if field in ("poli", "spesialisasi"):
        if val.upper() == "THT":
            return "THT"
        words = val.split()
        capitalized_words = []
        for w in words:
            if w.upper() == "THT":
                capitalized_words.append("THT")
            else:
                capitalized_words.append(w[0].upper() + w[1:].lower() if len(w) > 0 else "")
        return " ".join(capitalized_words)

    if field == "jenis_kelamin":
        lowered = val.lower()
        if "laki" in lowered:
            return "Laki-laki"
        if "perempuan" in lowered or "wanita" in lowered:
            return "Perempuan"
        return val.title()

    return val


def _build_filter(filters: dict | None) -> dict:
    """Convert a simple filter dict to an OpenSearch bool/filter query."""
    if not filters:
        return {"match_all": {}}

    must = []
    for field, value in filters.items():
        if isinstance(value, dict) and ("gte" in value or "lte" in value):
            must.append({"range": {field: value}})
        else:
            normalized_value = _normalize_filter_value(field, value)
            must.append({"term": {field: normalized_value}})

    return {"bool": {"filter": must}}


def _extract_aggs(res: dict) -> dict:
    return {k: v["value"] for k, v in res["aggregations"].items()}