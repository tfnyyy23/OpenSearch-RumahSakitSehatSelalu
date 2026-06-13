"""
gemini_client.py
----------------
Two responsibilities:
1. parse_intent()  -- translate user question to structured query params
2. format_answer() -- turn raw aggregation data into natural language answer
"""

import os
import json
import re

_genai = None
_genai_error = None


def _get_model():
    global _genai, _genai_error

    if _genai_error is not None:
        return None

    if _genai is None:
        try:
            import google.generativeai as genai

            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key or api_key.strip() == "":
                _genai_error = Exception("GEMINI_API_KEY is not set.")
                return None

            genai.configure(api_key=api_key)
            _genai = genai.GenerativeModel("gemini-1.5-flash")
        except Exception as exc:
            _genai_error = exc
            return None

    return _genai


# ---------------------------------------------------------------------------
# Intent parsing
# ---------------------------------------------------------------------------

INTENT_PROMPT = """
Kamu adalah sistem analitik biaya rumah sakit. Tugasmu adalah mengklasifikasikan pertanyaan pengguna ke dalam salah satu query_type dan mengekstrak filter yang relevan.

Query types yang tersedia:
- summary              : ringkasan umum biaya keseluruhan
- total_per_komponen   : total biaya per komponen (obat, tindakan, kamar, dokter)
- rata_rata            : rata-rata biaya per komponen
- per_poli             : biaya dikelompokkan per poli
- per_spesialisasi     : biaya dikelompokkan per spesialisasi dokter
- per_bulan            : tren biaya per bulan
- per_status_kunjungan : biaya per status kunjungan (rawat inap, rawat jalan, darurat)
- metode_bayar         : distribusi metode pembayaran
- out_of_scope         : pertanyaan di luar lingkup analitik biaya rumah sakit Sehat Selalu (seperti pertanyaan medis umum, keluhan klinis pasien, info/jadwal dokter, obrolan santai, dll.)

Filter yang bisa diekstrak (semua opsional):
- poli         : string, contoh "Mata", "Anak", "Jantung"
- spesialisasi : string, contoh "Ortopedi", "Kardiologi"
- status_kunjungan : string, contoh "rawat inap", "rawat jalan", "darurat"
- metode_bayar : string, contoh "Transfer", "Tunai", "Kartu Kredit"
- jenis_kelamin : string, "Laki-laki" atau "Perempuan"

Pertanyaan: "{question}"

Jawab HANYA dengan JSON valid, tanpa teks lain, tanpa markdown:
{{
  "query_type": "...",
  "filters": {{}}
}}
"""


def parse_intent(question: str) -> dict:
    """Returns dict with query_type and filters."""
    model = _get_model()
    if model is None:
        lowered = question.lower()
        
        # Fallback out-of-scope check: if no financial/cost keyword is present
        cost_keywords = ["biaya", "tarif", "harga", "tagihan", "dana", "pendapatan", "bayar", "uang", "rupiah", "rp", "tren", "distribusi", "rata-rata", "total", "spend", "cost", "bill"]
        has_cost_keyword = any(kw in lowered for kw in cost_keywords)
        if not has_cost_keyword:
            return {"query_type": "out_of_scope", "filters": {}}

        query_type = "summary"

        if "rata-rata" in lowered or "rata rata" in lowered:
            query_type = "rata_rata"
        elif "per komponen" in lowered or "total" in lowered:
            query_type = "total_per_komponen"
        elif "per poli" in lowered or "poli" in lowered:
            query_type = "per_poli"
        elif "spesialis" in lowered:
            query_type = "per_spesialisasi"
        elif "per bulan" in lowered or "bulanan" in lowered or "bulan" in lowered:
            query_type = "per_bulan"
        elif "status kunjungan" in lowered or "rawat inap" in lowered or "rawat jalan" in lowered or "darurat" in lowered:
            query_type = "per_status_kunjungan"
        elif "metode bayar" in lowered or "pembayaran" in lowered:
            query_type = "metode_bayar"

        filters = {}
        if "rawat inap" in lowered:
            filters["status_kunjungan"] = "rawat inap"
        elif "rawat jalan" in lowered:
            filters["status_kunjungan"] = "rawat jalan"
        elif "darurat" in lowered:
            filters["status_kunjungan"] = "darurat"

        return {"query_type": query_type, "filters": filters}

    prompt = INTENT_PROMPT.format(question=question)
    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"```json|```", "", raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback ke summary kalau parsing gagal
        return {"query_type": "summary", "filters": {}}


# ---------------------------------------------------------------------------
# Answer formatting
# ---------------------------------------------------------------------------

FORMAT_PROMPT = """
Kamu adalah analis biaya operasional rumah sakit. Sajikan data berikut dalam bahasa Indonesia yang jelas, ringkas, dan mudah dipahami oleh manajemen rumah sakit.

Pertanyaan pengguna: "{question}"

Data hasil query:
{data}

Instruksi:
- Gunakan format angka Rupiah (contoh: Rp 1.234.567)
- Jika data berisi beberapa kategori, tampilkan dalam bentuk list yang rapi
- Berikan insight singkat 1-2 kalimat di akhir jika relevan
- Jangan sebut nama variabel teknis seperti "biaya_obat", ganti dengan "Biaya Obat"
- Jawaban maksimal 200 kata
"""


def format_answer(question: str, data: dict) -> str:
    """Turn raw aggregation data into a readable natural language answer."""
    model = _get_model()
    if model is None:
        if not data:
            return "Tidak ada data yang tersedia untuk dijelaskan."

        return json.dumps(data, ensure_ascii=False, indent=2)

    response = model.generate_content(prompt)
    return response.text.strip()


# ---------------------------------------------------------------------------
# Out-of-Scope handling
# ---------------------------------------------------------------------------

OUT_OF_SCOPE_PROMPT = """
Kamu adalah asisten analisis biaya operasional Rumah Sakit Sehat Selalu.
Pertanyaan pengguna berikut di luar lingkup tugasmu:
"{question}"

Instruksi:
1. Berikan jawaban penolakan yang sopan, ramah, dan profesional dalam Bahasa Indonesia.
2. Jelaskan secara singkat bahwa tugasmu hanya berkaitan dengan analisis biaya operasional rumah sakit (seperti biaya obat, tindakan, kamar, tarif dokter, tren biaya bulanan, poli, metode pembayaran, atau keuangan).
3. Berikan contoh 2-3 pertanyaan analitis biaya rumah sakit yang bisa diajukan (misal: "Berapa total biaya operasional?", "Poli mana yang menghabiskan biaya terbesar?", "Bagaimana tren biaya per bulan?").
4. Jawaban maksimal 80 kata.
"""


def format_out_of_scope_answer(question: str) -> str:
    """Politely explain that the query is out of scope and give cost question examples."""
    model = _get_model()
    if model is None:
        return (
            "Maaf, pertanyaan Anda berada di luar lingkup analisis biaya operasional Rumah Sakit Sehat Selalu. "
            "Saya hanya dapat membantu Anda menganalisis data keuangan rumah sakit seperti tren biaya kamar, obat, tindakan, atau dokter.\n\n"
            "Contoh pertanyaan:\n"
            "- Berapa total biaya operasional rumah sakit?\n"
            "- Poli mana yang menghabiskan biaya terbesar?\n"
            "- Bagaimana tren biaya per bulan?"
        )

    prompt = OUT_OF_SCOPE_PROMPT.format(question=question)
    response = model.generate_content(prompt)
    return response.text.strip()