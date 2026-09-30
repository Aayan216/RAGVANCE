from typing import List, Dict, Any, Optional
from django.conf import settings
from .rag_chain import RAGChain
from .batch_generation import run_generation
from .grounding import make_grounding_validator


class MCQGenerator:
    def __init__(self, rag_chain: RAGChain = None):
        self.rag_chain = rag_chain or RAGChain()

    def generate_practice_set(
        self, 
        num_questions: int = 5, 
        difficulty: str = "medium",
        topic: str = None,
        doc_ids: List[int] = None,
    ) -> List[Dict[str, Any]]:
        """Generate exactly num_questions MCQs using concurrent multi-question batches."""
        per_call = getattr(settings, "PRACTICE_QUESTIONS_PER_LLM_CALL", 5)
        concurrency = getattr(settings, "PRACTICE_BATCH_SIZE", 3)

        def request_one_call(call_index: int, count: int) -> List[Dict[str, Any]]:
            # Corpus-derived seed per batch, rotating across requests (None -> "key concepts").
            query_topic = topic or self.rag_chain.next_practice_query(doc_ids)
            return self.rag_chain.generate_mcq_batch(
                topic=query_topic,
                difficulty=difficulty,
                doc_ids=doc_ids,
                count=count,
            )

        valid, stats = run_generation(
            request_one_call,
            requested=num_questions,
            per_call=per_call,
            concurrency=concurrency,
            log_label="Practice",
            extra_validate=make_grounding_validator(self.rag_chain.vector_store),
        )
        return valid

    def evaluate_answer(self, mcq: Dict[str, Any], selected: str) -> Dict[str, Any]:
        """Evaluate user's answer to an MCQ."""
        correct = mcq.get("correct", "").upper()
        is_correct = selected.upper() == correct
        return {
            "is_correct": is_correct,
            "correct_answer": correct,
            "selected": selected.upper(),
            "explanation": mcq.get("explanation", ""),
            "topic": mcq.get("topic", ""),
        }
