"""
Backend: qa_system_api.py
Deskripsi: REST API untuk QA System Rumah Sakit Sehat Selalu
           Menggunakan FastAPI + OpenSearch 

Jalankan dengan: uvicorn qa_system_api:app --reload --port 8000
"""

import os
import json
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from opensearchpy import OpenSearch
# import anthropic

# ============================================================
# KONFIGURASI
# ============================================================
OPENSEARCH_HOST = os.getenv("OPENSEARCH_HOST", "localhost")
OPENSEARCH_PORT = int(os.getenv("OPENSEARCH_PORT", 9200))
OPENSEARCH_USER = os.getenv("OPENSEARCH_USER", "admin")
OPENSEARCH_PASS = os.getenv("OPENSEARCH_PASS", "admin")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "YOUR_API_KEY_HERE")
INDEX_NAME = "rumah_sakit"

# ============================================================
# INISIALISASI CLIENT
# ============================================================
os_client = OpenSearch(
    hosts=[{"host": OPENSEARCH_HOST, "port": OPENSEARCH_PORT}],
    http_auth=(OPENSEARCH_USER, OPENSEARCH_PASS),
    use_ssl=False,
    verify_certs=False,
    ssl_show_warn=False,
)

# ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ============================================================
# FASTAPI APP
# ============================================================
app = FastAPI(
    title="QA System - Rumah Sakit Sehat Selalu",
    description="Question Answer System berbasis OpenSearch dan Claude AI",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# SCHEMA
# ============================================================
class QuestionRequest(BaseModel):
    question: str
    top_k: Optional[int] = 5
    doc_types: Optional[list] = None  # filter: ["dokter","pasien","registrasi","tagihan"]

class SearchRequest(BaseModel):
    query: str
    doc_type: Optional[str] = None
    size: Optional[int] = 10

# ============================================================
# FUNGSI OPENSEARCH
# ============================================================

def search_opensearch(query: str, doc_types: list = None, top_k: int = 5) -> list:
    """
    Melakukan full-text search di OpenSearch menggunakan multi_match query.
    Menggabungkan hasil dari field 'content', 'keluhan', 'nama_pasien', dll.
    """
    must_clauses = [
        {
            "multi_match": {
                "query": query,
                "fields": [
                    "content^3",
                    "keluhan^2",
                    "nama_pasien^2",
                    "nama_dokter^2",
                    "spesialisasi^1.5",
                    "alamat",
                    "poli"
                ],
                "type": "best_fields",
                "fuzziness": "AUTO"
            }
        }
    ]

    filter_clauses = []

    if doc_types:
        filter_clauses.append({"terms": {"doc_type": doc_types}})
    else:
        if "dokter" in query.lower() or "spesialis" in query.lower():
            filter_clauses.append({"term": {"doc_type": "dokter"}})

    body = {
        "query": {
            "bool": {
                "must": must_clauses,
                "filter": filter_clauses
            }
        },
        "size": top_k,
        "_source": True,
        "highlight": {
            "fields": {
                "content": {"fragment_size": 200, "number_of_fragments": 2},
                "keluhan": {}
            }
        }
    }

    response = os_client.search(index=INDEX_NAME, body=body)
    hits = response["hits"]["hits"]
    return hits


def aggregate_stats() -> dict:
    """Ambil statistik umum dari OpenSearch menggunakan aggregation"""
    body = {
        "size": 0,
        "aggs": {
            "by_type": {"terms": {"field": "doc_type"}},
            "by_spesialisasi": {"terms": {"field": "spesialisasi", "size": 20}},
            "by_poli": {"terms": {"field": "poli", "size": 20}},
            "by_status_kunjungan": {"terms": {"field": "status_kunjungan"}},
            "by_metode_bayar": {"terms": {"field": "metode_bayar", "size": 10}},
            "total_tagihan": {"sum": {"field": "total_bill"}},
            "avg_tagihan": {"avg": {"field": "total_bill"}},
            "tagihan_lunas": {
                "filter": {"term": {"status_bayar": True}},
                "aggs": {"count": {"value_count": {"field": "bills_id"}}}
            }
        }
    }
    response = os_client.search(index=INDEX_NAME, body=body)
    return response["aggregations"]


# ============================================================
# FUNGSI AI (CLAUDE)
# ============================================================

def build_context(hits: list) -> str:
    """Susun konteks dari hasil pencarian OpenSearch"""
    context_parts = []
    for i, hit in enumerate(hits, 1):
        src = hit["_source"]
        doc_type = src.get("doc_type", "unknown")
        content = src.get("content", "")
        score = round(hit["_score"], 3)
        context_parts.append(
            f"[Dokumen {i} | Tipe: {doc_type.upper()} | Score: {score}]\n{content}"
        )
    return "\n\n".join(context_parts)


# def ask_claude(question: str, context: str) -> str:
#     """Kirim pertanyaan + konteks ke Claude AI untuk mendapatkan jawaban"""
#     system_prompt = """Anda adalah asisten cerdas untuk sistem informasi Rumah Sakit Sehat Selalu.
# Anda memiliki akses ke data pasien, dokter, registrasi kunjungan, dan tagihan rumah sakit.

# ATURAN PENTING:
# 1. Jawab HANYA berdasarkan konteks yang diberikan
# 2. Jika informasi tidak tersedia dalam konteks, katakan "Informasi tidak ditemukan dalam database"
# 3. Format angka rupiah dengan titik sebagai pemisah ribuan (contoh: Rp 1.500.000)
# 4. Berikan jawaban yang jelas, terstruktur, dan profesional dalam Bahasa Indonesia
# 5. Jika ada data numerik/statistik, tampilkan dengan rapi
# 6. Jaga kerahasiaan data pasien - jangan berikan informasi lebih dari yang ditanyakan"""

#     user_message = f"""Berdasarkan data berikut dari database Rumah Sakit Sehat Selalu:

# {context}

# ---
# PERTANYAAN: {question}

# Tolong berikan jawaban yang akurat dan informatif berdasarkan data di atas."""

#     message = ai_client.messages.create(
#         model="claude-sonnet-4-6",
#         max_tokens=1024,
#         system=system_prompt,
#         messages=[{"role": "user", "content": user_message}]
#     )
#     return message.content[0].text

def simple_answer(question: str, hits: list) -> str:
    if not hits:
        return "Tidak ditemukan data yang relevan dalam database Rumah Sakit Sehat Selalu."

    context = build_context(hits)

    return f"""Berikut hasil pencarian dari database Rumah Sakit Sehat Selalu:

{context}

---

Jawaban diambil langsung dari data OpenSearch (tanpa AI)."""

# ============================================================
# ENDPOINT API
# ============================================================

@app.get("/")
def root():
    return {
        "app": "QA System - Rumah Sakit Sehat Selalu",
        "version": "1.0.0",
        "endpoints": ["/ask", "/search", "/stats", "/health"]
    }


@app.get("/health")
def health_check():
    """Cek status koneksi OpenSearch"""
    try:
        info = os_client.info()
        count = os_client.count(index=INDEX_NAME)["count"]
        return {
            "status": "healthy",
            "opensearch_version": info["version"]["number"],
            "total_documents": count
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"OpenSearch tidak tersedia: {str(e)}")


@app.post("/ask")
def ask_question(req: QuestionRequest):
    """
    Endpoint utama QA System:
    1. Cari dokumen relevan di OpenSearch
    2. Susun konteks
    3. Kirim ke Claude AI
    4. Return jawaban
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Pertanyaan tidak boleh kosong")

    # Step 1: Retrieve dari OpenSearch
    hits = search_opensearch(
        query=req.question,
        doc_types=req.doc_types,
        top_k=req.top_k
    )

    if not hits:
        return {
            "question": req.question,
            "answer": "Tidak ditemukan data yang relevan dalam database Rumah Sakit Sehat Selalu.",
            "sources": [],
            "total_sources": 0
        }

    # Step 2: Build context
    context = build_context(hits)

    # Step 3: Ask Claude AI
    # answer = ask_claude(req.question, context)
    answer = simple_answer(req.question, hits)

    # Step 4: Susun sources
    sources = []
    for hit in hits:
        src = hit["_source"]
        sources.append({
            "doc_type": src.get("doc_type"),
            "doc_id": src.get("doc_id"),
            "score": round(hit["_score"], 3),
            "preview": src.get("content", "")[:150] + "..."
        })

    return {
        "question": req.question,
        "answer": answer,
        "sources": sources,
        "total_sources": len(sources)
    }


@app.post("/search")
def search_documents(req: SearchRequest):
    """Endpoint pencarian dokumen langsung (tanpa AI)"""
    filter_types = [req.doc_type] if req.doc_type else None
    hits = search_opensearch(
        query=req.query,
        doc_types=filter_types,
        top_k=req.size
    )

    results = []
    for hit in hits:
        src = hit["_source"]
        results.append({
            "doc_type": src.get("doc_type"),
            "doc_id": src.get("doc_id"),
            "score": round(hit["_score"], 3),
            "content": src.get("content", ""),
            "data": {k: v for k, v in src.items() if k not in ["content", "doc_type", "doc_id"]}
        })

    return {
        "query": req.query,
        "total": len(results),
        "results": results
    }


@app.get("/stats")
def get_statistics():
    """Endpoint statistik ringkasan data rumah sakit"""
    try:
        aggs = aggregate_stats()

        # Parse aggregation results
        def parse_buckets(agg_key):
            return {b["key"]: b["doc_count"] for b in aggs[agg_key]["buckets"]}

        return {
            "ringkasan": {
                "total_dokumen": sum(b["doc_count"] for b in aggs["by_type"]["buckets"]),
                "dokter": next((b["doc_count"] for b in aggs["by_type"]["buckets"] if b["key"] == "dokter"), 0),
                "pasien": next((b["doc_count"] for b in aggs["by_type"]["buckets"] if b["key"] == "pasien"), 0),
                "registrasi": next((b["doc_count"] for b in aggs["by_type"]["buckets"] if b["key"] == "registrasi"), 0),
                "tagihan": next((b["doc_count"] for b in aggs["by_type"]["buckets"] if b["key"] == "tagihan"), 0),
            },
            "spesialisasi_dokter": parse_buckets("by_spesialisasi"),
            "poli_kunjungan": parse_buckets("by_poli"),
            "status_kunjungan": parse_buckets("by_status_kunjungan"),
            "metode_pembayaran": parse_buckets("by_metode_bayar"),
            "keuangan": {
                "total_tagihan_seluruh": aggs["total_tagihan"]["value"],
                "rata_rata_tagihan": round(aggs["avg_tagihan"]["value"] or 0, 2),
                "tagihan_lunas": aggs["tagihan_lunas"]["count"]["value"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/contoh-pertanyaan")
def contoh_pertanyaan():
    """Contoh pertanyaan yang bisa diajukan ke QA System"""
    return {
        "contoh_pertanyaan": [
            "Siapa dokter spesialis jantung di rumah sakit ini?",
            "Berapa total tagihan pasien dengan golongan darah A?",
            "Dokter mana yang paling banyak menangani pasien?",
            "Apa saja metode pembayaran yang tersedia?",
            "Berapa rata-rata tagihan rawat inap?",
            "Pasien mana yang paling sering datang ke poli mata?",
            "Berapa banyak kunjungan darurat yang tercatat?",
            "Dokter apa spesialisasi Dr. Balidin Dongoran?",
            "Berapa total pendapatan rumah sakit dari BPJS?",
            "Siapa pasien dengan tagihan tertinggi?"
        ]
    }
