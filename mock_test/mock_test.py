import json
import time
from typing import List, Dict, Any
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from core.models import MockTest, TestQuestion, TestAttempt, UserAnswer
from rag.rag_chain import RAGChain
from rag.batch_generation import run_generation, validate_mcq


class MockTestService:
    def __init__(self, rag_chain: RAGChain = None):
        self.rag_chain = rag_chain or RAGChain()

    _validate_mcq = staticmethod(validate_mcq)

    def create_test(
        self,
        num_questions: int = 20,
        difficulty: str = "medium",
        timer_minutes: int = 30,
        doc_ids: list = None,
        question_type: str = "mcq",
    ) -> MockTest:
        """Generate questions in concurrent multi-question batches and create a MockTest.

        question_type: "mcq", "true_false", or "both".
        For "both": true_false_count = 30% of num_questions,
        mcq_count = 70% of num_questions (remainder).
        The final test always contains exactly num_questions questions.
        """
        per_call = getattr(settings, "MOCK_TEST_QUESTIONS_PER_LLM_CALL", 5)
        concurrency = getattr(settings, "MOCK_TEST_BATCH_SIZE", 3)

        if question_type == "mcq":
            mcq_count, tf_count = num_questions, 0
        elif question_type == "true_false":
            mcq_count, tf_count = 0, num_questions
        elif question_type == "both":
            tf_count = int(round(num_questions * 0.3))
            mcq_count = num_questions - tf_count
        else:
            raise ValueError("Invalid question type.")

        shared_state = {}

        def make_request(qtype: str):
            def request_one_call(call_index: int, count: int) -> List[Dict[str, Any]]:
                return self.rag_chain.generate_mock_questions_batch(
                    difficulty=difficulty,
                    doc_ids=doc_ids,
                    count=count,
                    question_type=qtype,
                )
            return request_one_call

        mcqs: List[Dict[str, Any]] = []
        true_falses: List[Dict[str, Any]] = []
        if mcq_count > 0:
            mcqs, _ = run_generation(
                make_request("mcq"),
                requested=mcq_count,
                per_call=per_call,
                concurrency=concurrency,
                log_label="Mock Test",
                shared_state=shared_state,
            )
        if tf_count > 0:
            true_falses, _ = run_generation(
                make_request("true_false"),
                requested=tf_count,
                per_call=per_call,
                concurrency=concurrency,
                log_label="Mock Test T/F",
                shared_state=shared_state,
            )

        ordered = self._interleave(mcqs, true_falses, num_questions)

        test = MockTest.objects.create(
            num_questions=num_questions,
            difficulty=difficulty,
            timer_minutes=timer_minutes,
            doc_ids=doc_ids or [],
            status="created",
        )

        questions = [
            TestQuestion(
                test=test,
                question_text=q["question"],
                question_type=q.get("question_type", "mcq"),
                option_a=q["options"]["A"],
                option_b=q["options"]["B"],
                option_c=q["options"].get("C", ""),
                option_d=q["options"].get("D", ""),
                correct_answer=q["correct"],
                difficulty=difficulty,
                topic=q.get("topic", ""),
                explanation=q.get("explanation", ""),
                source_chunk_ids=q.get("source_chunks", []),
            )
            for q in ordered
        ]
        TestQuestion.objects.bulk_create(questions)
        return test

    @staticmethod
    def _interleave(
        mcqs: List[Dict[str, Any]],
        true_falses: List[Dict[str, Any]],
        total: int,
    ) -> List[Dict[str, Any]]:
        """Merge MCQ and True/False questions at deterministic positions.

        True/False position i (0-based) is placed at 1-based position:
            floor((i + 1) * (total + 1) / (len(true_falses) + 1) + 0.5)
        This spreads them naturally (e.g. 10 questions -> positions 3, 6, 8)
        while keeping the exact total.
        """
        tf_count = len(true_falses)
        if tf_count == 0:
            return list(mcqs)
        if not mcqs:
            return list(true_falses)

        tf_positions = set()
        for i in range(tf_count):
            pos = int((i + 1) * (total + 1) / (tf_count + 1) + 0.5)
            pos = min(max(pos, 1), total)
            tf_positions.add(pos)

        ordered: List[Dict[str, Any]] = []
        mcq_iter = iter(mcqs)
        tf_iter = iter(true_falses)
        for pos in range(1, total + 1):
            if pos in tf_positions:
                ordered.append(next(tf_iter))
            else:
                ordered.append(next(mcq_iter))
        return ordered

    def get_test_questions(self, test_id: int) -> List[TestQuestion]:
        return list(TestQuestion.objects.filter(test_id=test_id).order_by("id"))

    def submit_attempt(
        self,
        test_id: int,
        answers: Dict[int, str],
        time_taken_seconds: int,
    ) -> TestAttempt:
        """Grade the test and update existing attempt with answers."""
        test = MockTest.objects.get(id=test_id)

        attempt = TestAttempt.objects.filter(test=test).first()
        if not attempt:
            raise ValueError("No attempt found for this test.")
        if attempt.status == "completed":
            raise ValueError("This test has already been submitted.")
        if attempt.status == "terminated":
            raise ValueError("This test has been terminated.")

        questions = self.get_test_questions(test_id)

        score = 0
        user_answers = []

        for q in questions:
            selected = answers.get(q.id, "").upper()
            is_correct = selected == q.correct_answer
            if is_correct:
                score += 1

            user_answers.append(UserAnswer(
                attempt=None,
                question=q,
                selected_option=selected,
                is_correct=is_correct,
            ))

        percentage = (score / len(questions)) * 100 if questions else 0

        with transaction.atomic():
            attempt.score = score
            attempt.total_questions = len(questions)
            attempt.percentage = percentage
            attempt.time_taken_seconds = time_taken_seconds
            attempt.completed_at = timezone.now()
            attempt.status = "completed"
            attempt.save()

            test.status = "completed"
            test.save()

            for ua in user_answers:
                ua.attempt = attempt
            UserAnswer.objects.bulk_create(user_answers)

        return attempt

    def terminate_attempt(self, test_id: int, attempt_id: int) -> TestAttempt:
        """Mark a test attempt as terminated (e.g., fullscreen exit)."""
        test = MockTest.objects.get(id=test_id)
        attempt = TestAttempt.objects.get(id=attempt_id, test=test)

        if attempt.status == "completed":
            return attempt

        attempt.status = "terminated"
        attempt.completed_at = timezone.now()
        attempt.save()

        test.status = "terminated"
        test.save()

        return attempt

    def get_attempt_result(self, attempt_id: int) -> Dict[str, Any]:
        """Get detailed result for an attempt."""
        attempt = TestAttempt.objects.select_related("test").get(id=attempt_id)
        answers = UserAnswer.objects.filter(attempt=attempt).select_related("question")

        correct_qs = []
        wrong_qs = []

        for ans in answers:
            q = ans.question
            data = {
                "question_id": q.id,
                "question_type": q.question_type,
                "question_text": q.question_text,
                "options": {
                    "A": q.option_a,
                    "B": q.option_b,
                    "C": q.option_c,
                    "D": q.option_d,
                },
                "correct_answer": q.correct_answer,
                "selected": ans.selected_option,
                "is_correct": ans.is_correct,
                "explanation": q.explanation,
                "topic": q.topic,
                "source_chunk_ids": q.source_chunk_ids,
            }
            if ans.is_correct:
                correct_qs.append(data)
            else:
                wrong_qs.append(data)

        return {
            "attempt": {
                "id": attempt.id,
                "score": attempt.score,
                "total": attempt.total_questions,
                "percentage": attempt.percentage,
                "time_taken_seconds": attempt.time_taken_seconds,
                "completed_at": attempt.completed_at,
            },
            "correct": correct_qs,
            "wrong": wrong_qs,
        }
