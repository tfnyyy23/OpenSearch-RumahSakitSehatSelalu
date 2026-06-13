"""
index_to_opensearch.py
----------------------
Create index 'tagihan_operasional' in OpenSearch and bulk-insert
all denormalized documents.

Prerequisites:
    pip install opensearch-py

Run from project root:
    python scripts/index_to_opensearch.py
"""

import json
import os
import sys
from opensearchpy import OpenSearch, helpers

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", 9200))
INDEX_NAME      = "tagihan_operasional"
DATA_PATH       = os.path.join("data", "processed", "tagihan_denormalized.json")

# ---------------------------------------------------------------------------
# Index mapping
# Tells OpenSearch the correct field types so aggregations work properly.
# Without this, numbers might be treated as strings.
# ---------------------------------------------------------------------------
INDEX_MAPPING = {
    "settings": {
        "number_of_shards":   1,
        "number_of_replicas": 0      # single-node setup, no replicas needed
    },
    "mappings": {
        "properties": {
            # -- Tagihan --
            "bills_id":         {"type": "keyword"},
            "register_id":      {"type": "keyword"},
            "total_bill":       {"type": "long"},
            "status_bayar":     {"type": "boolean"},
            "metode_bayar":     {"type": "keyword"},
            "bills_date":       {"type": "date", "format": "yyyy-MM-dd'T'HH:mm:ss"},
            # -- Rincian biaya --
            "biaya_dokter":     {"type": "long"},
            "biaya_obat":       {"type": "long"},
            "biaya_tindakan":   {"type": "long"},
            "biaya_kamar":      {"type": "long"},
            # -- Registrasi --
            "reg_date":         {"type": "date", "format": "yyyy-MM-dd'T'HH:mm:ss"},
            "keluhan":          {"type": "text"},
            "poli":             {"type": "keyword"},
            "status_kunjungan": {"type": "keyword"},
            # -- Dokter --
            "doctor_id":        {"type": "keyword"},
            "nama_dokter":      {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "spesialisasi":     {"type": "keyword"},
            # -- Pasien --
            "pasien_id":        {"type": "keyword"},
            "nama_pasien":      {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "jenis_kelamin":    {"type": "keyword"},
            "golongan_darah":   {"type": "keyword"},
        }
    }
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_client() -> OpenSearch:
    client = OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
        use_ssl=False,
        verify_certs=False,
        http_compress=True,
    )
    info = client.info()
    print(f"  Connected to OpenSearch {info['version']['number']} "
          f"(cluster: {info['cluster_name']})")
    return client


def create_index(client: OpenSearch) -> None:
    if client.indices.exists(index=INDEX_NAME):
        print(f"  Index '{INDEX_NAME}' already exists -- deleting and recreating ...")
        client.indices.delete(index=INDEX_NAME)

    client.indices.create(index=INDEX_NAME, body=INDEX_MAPPING)
    print(f"  Index '{INDEX_NAME}' created with mapping.")


def generate_actions(documents: list[dict]):
    """Yield bulk action dicts for opensearch-py helpers.bulk."""
    for doc in documents:
        yield {
            "_index": INDEX_NAME,
            "_id":    doc["bills_id"],   # use bills_id as document ID (idempotent)
            "_source": doc,
        }


def bulk_index(client: OpenSearch, documents: list[dict]) -> None:
    print(f"  Indexing {len(documents)} documents ...")
    success, failed = helpers.bulk(
        client,
        generate_actions(documents),
        chunk_size=200,
        raise_on_error=False,
    )
    print(f"  Success : {success}")
    if failed:
        print(f"  Failed  : {len(failed)}")
        for err in failed[:5]:     # print first 5 errors only
            print(f"    {err}")
    else:
        print(f"  Failed  : 0")


def verify(client: OpenSearch) -> None:
    client.indices.refresh(index=INDEX_NAME)
    count = client.count(index=INDEX_NAME)["count"]
    print(f"  Document count in '{INDEX_NAME}': {count}")

    # Quick sample aggregation -- total biaya per komponen
    agg_query = {
        "size": 0,
        "aggs": {
            "total_biaya_dokter":   {"sum": {"field": "biaya_dokter"}},
            "total_biaya_obat":     {"sum": {"field": "biaya_obat"}},
            "total_biaya_tindakan": {"sum": {"field": "biaya_tindakan"}},
            "total_biaya_kamar":    {"sum": {"field": "biaya_kamar"}},
        }
    }
    res = client.search(index=INDEX_NAME, body=agg_query)
    aggs = res["aggregations"]
    print("\n  Sample aggregation -- total biaya keseluruhan:")
    for key, val in aggs.items():
        formatted = f"Rp {val['value']:,.0f}"
        print(f"    {key:<25} : {formatted}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n[1/4] Connecting to OpenSearch ...")
    try:
        client = get_client()
    except Exception as e:
        print(f"  ERROR: Cannot connect to OpenSearch -- {e}")
        sys.exit(1)

    print("\n[2/4] Creating index ...")
    create_index(client)

    print("\n[3/4] Loading denormalized data ...")
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        documents = json.load(f)
    print(f"  Loaded {len(documents)} documents from {DATA_PATH}")

    print("\n[4/4] Bulk indexing ...")
    bulk_index(client, documents)

    print("\n[Verify] Checking index ...")
    verify(client)

    print("\nDone. OpenSearch index is ready.\n")


if __name__ == "__main__":
    main()