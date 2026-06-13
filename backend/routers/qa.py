"""
routers/qa.py
-------------
Endpoint: POST /ask
Flow:
  1. Gemini parse intent dari pertanyaan user
  2. Pilih dan jalankan query OpenSearch yang sesuai
  3. Gemini format hasil jadi natural language
  4. Return ke client
"""

from fastapi import APIRouter, HTTPException
from backend.models.schemas import QuestionRequest, QuestionResponse
from backend.services import opensearch_client as os_client
from backend.services import gemini_client as gemini

router = APIRouter()

# Map query_type ke fungsi OpenSearch yang sesuai
QUERY_MAP = {
    "summary":              os_client.summary_stats,
    "total_per_komponen":   os_client.total_biaya_per_komponen,
    "rata_rata":            os_client.rata_rata_biaya_per_komponen,
    "per_poli":             os_client.biaya_per_poli,
    "per_spesialisasi":     os_client.biaya_per_spesialisasi,
    "per_bulan":            os_client.biaya_per_bulan,
    "per_status_kunjungan": os_client.biaya_per_status_kunjungan,
    "metode_bayar":         os_client.metode_bayar_distribution,
}


@router.post("/ask", response_model=QuestionResponse)
async def ask(request: QuestionRequest):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Pertanyaan tidak boleh kosong.")

    # Step 1 -- parse intent
    try:
        intent = gemini.parse_intent(question)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini intent parsing error: {e}")

    query_type = intent.get("query_type", "summary")
    filters    = intent.get("filters", {}) or {}

    # Fallback ke summary kalau query_type tidak dikenal
    query_fn = QUERY_MAP.get(query_type, os_client.summary_stats)

    # Step 2 -- run OpenSearch query
    try:
        data = query_fn(filters if filters else None)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OpenSearch query error: {e}")

    # Step 3 -- format answer
    try:
        answer = gemini.format_answer(question, data)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini format error: {e}")

    return QuestionResponse(
        question=question,
        answer=answer,
        data=data,
        query_type=query_type,
    )


@router.get("/health")
async def health():
    try:
        client = os_client.get_client()
        info   = client.info()
        return {
            "status":           "ok",
            "opensearch":       info["version"]["number"],
            "cluster":          info["cluster_name"],
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))