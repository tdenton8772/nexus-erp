"""
NNLM HTTP client.

NNLM is the multi-agent retrieval + grounded synthesis layer that sits on top
of NAM. It:
  1. Encodes a natural language query via its multi-agent pipeline
     (NAM encoding → supervisor → entity organizer → retrieval → quality gate)
  2. Returns a NAMPayload with grounded results and citations
  3. Decodes that payload into a grounded response string with [N] citation markers

The agent layer calls NNLM instead of the LLM directly for any operation that
needs to reference ERP schema definitions, past mappings, or sync history —
ensuring responses are grounded in indexed facts, not hallucinated.

Ports (from nnlm/python services):
  Encoder: NNLM_ENCODER_URL (default http://localhost:8001)
  Decoder: NNLM_DECODER_URL (default http://localhost:8002)
"""
import logging
from typing import Any, Optional

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)


class NNLMClient:
    """
    Wraps the NNLM encoder (/encode) and decoder (/decode) endpoints.

    Typical usage in the agent:

        payload = await nnlm.encode(
            "Map invoice fields between Sage Intacct and Dynamics 365",
            history=prior_messages,
        )
        if payload["quality"]["sufficient"]:
            response = await nnlm.decode(
                query="Map invoice fields...",
                payload=payload,
            )
    """

    def __init__(self) -> None:
        self._encoder_url = settings.nnlm_encoder_url
        self._decoder_url = settings.nnlm_decoder_url
        self._http = httpx.AsyncClient(timeout=60.0)

    async def close(self) -> None:
        await self._http.aclose()

    # ── Encode ─────────────────────────────────────────────────────────────────

    async def encode(
        self,
        text: str,
        history: Optional[list[str]] = None,
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Run the full NNLM multi-agent pipeline:
          text → NAM encoding → supervisor planning → retrieval → quality gate

        Returns EncodeResponse dict:
          {
            plan, entities, query_results, graph_results,
            session_results, session_turns, quality,
            errors, latency_ms, session_id, turn_index
          }

        quality.sufficient=True means enough grounded context was retrieved
        for the decoder to synthesize a reliable answer.
        """
        payload = {
            "text": text,
            "history": history or [],
            "session_id": session_id,
        }
        try:
            resp = await self._http.post(f"{self._encoder_url}/encode", json=payload)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("NNLM encode failed: %s", exc)
            return {
                "plan": {},
                "entities": [],
                "query_results": [],
                "graph_results": [],
                "session_results": [],
                "session_turns": [],
                "quality": {"sufficient": False, "result_count": 0, "needs_broadening": True, "action": None},
                "errors": [str(exc)],
                "latency_ms": 0,
                "session_id": session_id,
                "turn_index": 0,
            }

    # ── Decode ─────────────────────────────────────────────────────────────────

    async def decode(
        self,
        query: str,
        payload: dict[str, Any],
        max_length: int = 512,
    ) -> dict[str, Any]:
        """
        Synthesize a grounded response from NNLM encoder output.

        Returns DecodeResponse dict:
          {
            response: str,          # grounded answer with [N] citation markers
            citations: [int],       # indices into query_results
            cited_record_ids: [str],
            gated: bool,            # True if quality gate blocked generation
            noise_copy_rate: float  # metric: fraction directly from source
          }
        """
        body = {
            "query": query,
            "payload": payload,
            "max_length": max_length,
        }
        try:
            resp = await self._http.post(f"{self._decoder_url}/decode", json=body)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("NNLM decode failed: %s", exc)
            return {
                "response": "",
                "citations": [],
                "cited_record_ids": [],
                "gated": True,
                "noise_copy_rate": None,
                "error": str(exc),
            }

    # ── Session ────────────────────────────────────────────────────────────────

    async def write_turn(
        self,
        session_id: str,
        turn_index: int,
        query: str,
        response: str,
        entities: list[dict],
        query_results: list[dict],
    ) -> bool:
        """Persist an agent Q&A turn to NAM for conversation continuity."""
        payload = {
            "session_id": session_id,
            "turn_index": turn_index,
            "query": query,
            "response": response,
            "entities": entities,
            "query_results": query_results,
        }
        try:
            resp = await self._http.post(f"{self._encoder_url}/write_turn", json=payload)
            resp.raise_for_status()
            return resp.json().get("ok", False)
        except Exception as exc:
            logger.error("NNLM write_turn failed: %s", exc)
            return False

    # ── Convenience: encode + decode in one call ───────────────────────────────

    async def query_and_synthesize(
        self,
        text: str,
        history: Optional[list[str]] = None,
        session_id: Optional[str] = None,
        max_length: int = 512,
    ) -> dict[str, Any]:
        """
        Full encode → decode pipeline in one call.
        Returns combined dict with both EncodeResponse and DecodeResponse fields.
        Falls back gracefully if NNLM is unavailable (quality.sufficient=False).
        """
        encode_result = await self.encode(text, history=history, session_id=session_id)

        if not encode_result.get("quality", {}).get("sufficient", False):
            logger.warning("NNLM quality gate: insufficient results for query: %s", text[:80])
            return {**encode_result, "response": "", "citations": [], "gated": True}

        decode_result = await self.decode(text, encode_result, max_length=max_length)

        # Persist turn
        if session_id and decode_result.get("response"):
            await self.write_turn(
                session_id=session_id,
                turn_index=encode_result.get("turn_index", 0),
                query=text,
                response=decode_result["response"],
                entities=encode_result.get("entities", []),
                query_results=encode_result.get("query_results", []),
            )

        return {**encode_result, **decode_result}

    # ── Health ─────────────────────────────────────────────────────────────────

    async def health(self) -> dict[str, bool]:
        results = {}
        for name, url in [("encoder", self._encoder_url), ("decoder", self._decoder_url)]:
            try:
                resp = await self._http.get(f"{url}/health", timeout=5.0)
                results[name] = resp.status_code == 200
            except Exception:
                results[name] = False
        return results
