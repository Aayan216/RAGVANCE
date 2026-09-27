import os
import json
import re
from typing import List, Dict, Any, Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from django.conf import settings
from .vector_store import VectorStore
from .embedder import Embedder


def _redact_secrets(text: str) -> str:
    """Prevent API keys from leaking into logs."""
    text = re.sub(r"(?i)([?&]key=)[^&\s\"']+", r"\1***", text)
    text = re.sub(r"AIza[0-9A-Za-z_\-]{10,}", "***", text)
    return text


TUTOR_PROMPT = PromptTemplate(
    input_variables=["context", "question"],
    template="""You are a study assistant. Answer the question using ONLY the provided context.
Give a direct, plain-text answer. No markdown. No bullet points. No bold. No formatting.
Keep it short and to the point. If context doesn't have enough info, say "I don't have enough information about this."

Context:
{context}

Question: {question}

Answer:"""
)

MCQ_PROMPT = PromptTemplate(
    input_variables=["context", "topic", "difficulty"],
    template="""Generate a multiple-choice question from the context.

Context:
{context}

Topic: {topic}
Difficulty: {difficulty}

Requirements:
- 4 options (A, B, C, D)
- One correct answer
- Include explanation of why the correct answer is right
- Question should test understanding, not just memorization

Output format (JSON):
{{
    "question": "Question text here",
    "options": {{"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"}},
    "correct": "A",
    "explanation": "Why the correct answer is right...",
    "topic": "Topic name"
}}"""
)

MOCK_PROMPT = PromptTemplate(
    input_variables=["context", "difficulty"],
    template="""Generate an exam-style multiple-choice question from the context.

Context:
{context}
Difficulty: {difficulty}

Requirements:
- 4 options (A, B, C, D)
- One correct answer
- Include explanation
- Tag with a specific topic/concept
- {difficulty} level: easy=basic recall, medium=application, hard=analysis/synthesis

Output format (JSON):
{{
    "question": "Question text here",
    "options": {{"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"}},
    "correct": "A",
    "explanation": "Why the correct answer is right...",
    "topic": "Specific topic/concept"
}}"""
)

MCQ_BATCH_PROMPT = PromptTemplate(
    input_variables=["context", "topic", "difficulty", "count"],
    template="""Generate exactly {count} multiple-choice questions from the context.

Context:
{context}

Topic: {topic}
Difficulty: {difficulty}

Requirements:
- Exactly {count} questions
- Each question: 4 options (A, B, C, D), one correct answer, explanation, topic tag
- {difficulty} level: easy=basic recall, medium=application, hard=analysis/synthesis
- Each question must focus on a DIFFERENT concept from the context where possible;
  do not ask several questions about the same idea
- Ground every question ONLY in the provided context; never invent facts,
  concepts, or details that are not in the context
- Question should test understanding, not just memorization

Output format (JSON only, no other text):
{{
    "questions": [
        {{
            "question": "Question text here",
            "options": {{"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"}},
            "correct": "A",
            "explanation": "Why the correct answer is right...",
            "topic": "Topic name"
        }}
    ]
}}"""
)

MOCK_BATCH_PROMPT = PromptTemplate(
    input_variables=["context", "difficulty", "count"],
    template="""Generate exactly {count} exam-style multiple-choice questions from the context.

Context:
{context}
Difficulty: {difficulty}

Requirements:
- Exactly {count} questions
- Each question: 4 options (A, B, C, D), one correct answer, explanation, specific topic tag
- {difficulty} level: easy=basic recall, medium=application, hard=analysis/synthesis
- Each question must focus on a DIFFERENT concept from the context where possible;
  do not ask several questions about the same idea
- Ground every question ONLY in the provided context; never invent facts,
  concepts, or details that are not in the context
- Questions should test understanding, not just memorization

Output format (JSON only, no other text):
{{
    "questions": [
        {{
            "question": "Question text here",
            "options": {{"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"}},
            "correct": "A",
            "explanation": "Why the correct answer is right...",
            "topic": "Specific topic/concept"
        }}
    ]
}}"""
)

TRUE_FALSE_BATCH_PROMPT = PromptTemplate(
    input_variables=["context", "difficulty", "count"],
    template="""Generate exactly {count} true/false exam questions from the context.

Context:
{context}
Difficulty: {difficulty}

Requirements:
- Exactly {count} questions
- Each question is a factual statement that is clearly TRUE or clearly FALSE according to the context
- Ground every statement ONLY in the provided context; do not rely on outside knowledge
- The statement must be directly supported or contradicted by the supplied context
- Each statement must have exactly one correct answer
- Avoid ambiguous wording, double negatives, and statements that are
  technically true under one interpretation and false under another
- {difficulty} level: easy=basic recall, medium=application, hard=analysis/synthesis
- Include an explanation grounded in the context for each statement
- Tag each with a specific topic/concept

Output format (JSON only, no other text):
{{
    "questions": [
        {{
            "question_type": "true_false",
            "question": "Statement here",
            "options": {{"A": "True", "B": "False"}},
            "correct": "A",
            "explanation": "Explanation grounded in the context...",
            "topic": "Specific topic/concept"
        }}
    ]
}}"""
)


class RAGChain:
    def __init__(self, vector_store: VectorStore = None, embedder: Embedder = None):
        self.vector_store = vector_store or VectorStore()
        self.embedder = embedder or Embedder()
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        
        model_name = getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.llm = ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model=model_name,
        )
        self.top_k = getattr(settings, "TOP_K_RETRIEVAL", 5)

    @staticmethod
    def _extract_text(response) -> str:
        content = response.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    parts.append(part["text"])
                elif isinstance(part, str):
                    parts.append(part)
            return " ".join(parts).strip()
        return str(content)

    def _retrieve_context(self, query: str, doc_ids: List[int] = None) -> List[Dict[str, Any]]:
        query_emb = self.embedder.embed_query(query)
        return self.vector_store.search(query_emb, k=self.top_k, doc_ids=doc_ids)

    def _format_context(self, results: List[Dict[str, Any]]) -> str:
        parts = []
        for r in results:
            doc_id = r.get("doc_id", "?")
            chunk_idx = r.get("chunk_index", "?")
            text = r.get("text", r.get("content", ""))
            parts.append(f"[doc_{doc_id}:chunk_{chunk_idx}] {text}")
        return "\n\n".join(parts)

    def tutor_query(self, question: str) -> Dict[str, Any]:
        """Tutor mode: Answer question with citations."""
        results = self._retrieve_context(question)
        if not results:
            return {"answer": "No relevant documents found. Please upload study materials first.", "sources": []}
        
        context = self._format_context(results)
        prompt = TUTOR_PROMPT.format(context=context, question=question)
        response = self.llm.invoke(prompt)
        answer = self._extract_text(response)
        
        sources = []
        for r in results:
            sources.append({
                "doc_id": r.get("doc_id"),
                "chunk_index": r.get("chunk_index"),
                "page_number": r.get("page_number"),
                "file_name": r.get("file_name"),
                "text": r.get("text", r.get("content", ""))[:200],
                "score": r.get("score"),
            })
        
        return {
            "answer": answer,
            "sources": sources,
        }

    @staticmethod
    def _extract_json(text: str) -> str:
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
        return clean.strip()

    def generate_mcq(self, topic: str = None, difficulty: str = "medium", doc_ids: List[int] = None) -> Dict[str, Any]:
        """Practice mode: Generate MCQ from context."""
        query = topic or "key concepts"
        results = self._retrieve_context(query, doc_ids=doc_ids)
        if not results:
            return {"error": "No content available. Upload documents first."}
        
        context = self._format_context(results)
        prompt = MCQ_PROMPT.format(context=context, topic=topic or "General", difficulty=difficulty)
        response = self.llm.invoke(prompt)
        raw_text = self._extract_text(response)
        clean_text = self._extract_json(raw_text)
        
        try:
            mcq = json.loads(clean_text)
            mcq["source_chunks"] = [r.get("faiss_id") for r in results]
            return mcq
        except json.JSONDecodeError:
            return {"error": "Failed to parse MCQ response", "raw": raw_text}

    def generate_mock_question(self, difficulty: str = "medium", doc_ids: List[int] = None) -> Dict[str, Any]:
        """Mock test mode: Generate exam question."""
        results = self._retrieve_context("important concepts for exam", doc_ids=doc_ids)
        if not results:
            return {"error": "No content available. Upload documents first."}
        
        context = self._format_context(results)
        prompt = MOCK_PROMPT.format(context=context, difficulty=difficulty)
        response = self.llm.invoke(prompt)
        raw_text = self._extract_text(response)
        clean_text = self._extract_json(raw_text)
        
        try:
            mcq = json.loads(clean_text)
            mcq["source_chunks"] = [r.get("faiss_id") for r in results]
            return mcq
        except json.JSONDecodeError:
            return {"error": "Failed to parse question", "raw": raw_text}

    def _parse_questions_list(self, text: str, expected: int) -> List[Dict[str, Any]]:
        """Parse a batch JSON response into a list of MCQ dicts."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict):
            questions = data.get("questions")
        elif isinstance(data, list):
            questions = data
        else:
            return []
        if not isinstance(questions, list):
            return []
        return [q for q in questions if isinstance(q, dict)][:expected]

    def generate_mcq_batch(
        self,
        topic: str = None,
        difficulty: str = "medium",
        doc_ids: List[int] = None,
        count: int = 5,
    ) -> List[Dict[str, Any]]:
        """Practice mode: generate multiple MCQs in one LLM call."""
        query = topic or "key concepts"
        results = self._retrieve_context(query, doc_ids=doc_ids)
        if not results:
            return []

        context = self._format_context(results)
        prompt = MCQ_BATCH_PROMPT.format(
            context=context,
            topic=topic or "General",
            difficulty=difficulty,
            count=count,
        )
        try:
            response = self.llm.invoke(prompt)
        except Exception as exc:
            print(
                f"[ERROR] practice MCQ batch failed | batch_count={count} | doc_ids={doc_ids} | "
                + _redact_secrets(f"{type(exc).__name__}: {exc}")
            )
            return []
        raw_text = self._extract_text(response)
        clean_text = self._extract_json(raw_text)
        questions = self._parse_questions_list(clean_text, count)
        for mcq in questions:
            mcq["source_chunks"] = [r.get("faiss_id") for r in results]
        return questions

    def generate_mock_questions_batch(
        self,
        difficulty: str = "medium",
        doc_ids: List[int] = None,
        count: int = 5,
        question_type: str = "mcq",
    ) -> List[Dict[str, Any]]:
        """Mock test mode: generate multiple exam questions in one LLM call.

        question_type is "mcq" or "true_false"; retrieval (FAISS + doc_ids
        filtering) is identical for both types.
        """
        results = self._retrieve_context("important concepts for exam", doc_ids=doc_ids)
        if not results:
            return []

        is_true_false = question_type == "true_false"
        prompt_template = TRUE_FALSE_BATCH_PROMPT if is_true_false else MOCK_BATCH_PROMPT
        context = self._format_context(results)
        prompt = prompt_template.format(
            context=context,
            difficulty=difficulty,
            count=count,
        )
        try:
            response = self.llm.invoke(prompt)
        except Exception as exc:
            print(
                f"[ERROR] mock {'true_false' if is_true_false else 'MCQ'} batch failed | batch_count={count} | doc_ids={doc_ids} | "
                + _redact_secrets(f"{type(exc).__name__}: {exc}")
            )
            return []
        raw_text = self._extract_text(response)
        clean_text = self._extract_json(raw_text)
        questions = self._parse_questions_list(clean_text, count)
        for question in questions:
            question["question_type"] = question_type
            question["source_chunks"] = [r.get("faiss_id") for r in results]
        return questions