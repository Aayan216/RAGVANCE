from typing import List, Dict, Any
from collections import defaultdict
import pandas as pd
from core.models import TestAttempt, UserAnswer, TestQuestion, PerformanceAnalysis


class PerformanceAnalyzer:
    def analyze(self, attempt: TestAttempt) -> PerformanceAnalysis:
        """Compute performance analysis for an attempt."""
        answers = UserAnswer.objects.filter(attempt=attempt).select_related("question")
        
        # Topic-wise analysis
        topic_stats = defaultdict(lambda: {"correct": 0, "total": 0})
        difficulty_stats = defaultdict(lambda: {"correct": 0, "total": 0})
        
        for ans in answers:
            q = ans.question
            topic = q.topic or "General"
            difficulty = q.difficulty
            
            topic_stats[topic]["total"] += 1
            difficulty_stats[difficulty]["total"] += 1
            
            if ans.is_correct:
                topic_stats[topic]["correct"] += 1
                difficulty_stats[difficulty]["correct"] += 1
        
        # Calculate accuracies
        topic_accuracy = {}
        for topic, stats in topic_stats.items():
            acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
            topic_accuracy[topic] = {
                "accuracy": round(acc, 2),
                "correct": stats["correct"],
                "total": stats["total"],
            }
        
        difficulty_breakdown = {}
        for diff, stats in difficulty_stats.items():
            acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
            difficulty_breakdown[diff] = {
                "accuracy": round(acc, 2),
                "correct": stats["correct"],
                "total": stats["total"],
            }
        
        # Sort topics by accuracy
        sorted_topics = sorted(topic_accuracy.items(), key=lambda x: x[1]["accuracy"])
        
        weak_topics = [
            {"topic": t, "accuracy": v["accuracy"], "correct": v["correct"], "total": v["total"]}
            for t, v in sorted_topics if v["accuracy"] < 0.7
        ][:5]
        
        strong_topics = [
            {"topic": t, "accuracy": v["accuracy"], "correct": v["correct"], "total": v["total"]}
            for t, v in sorted_topics if v["accuracy"] >= 0.7
        ][-5:]
        strong_topics.reverse()
        
        # Create or update analysis
        analysis, created = PerformanceAnalysis.objects.update_or_create(
            attempt=attempt,
            defaults={
                "weak_topics": weak_topics,
                "strong_topics": strong_topics,
                "difficulty_breakdown": difficulty_breakdown,
            }
        )
        
        return analysis

    def get_chart_data(self, attempt: TestAttempt) -> Dict[str, Any]:
        """Get data formatted for Chart.js."""
        analysis = attempt.analysis if hasattr(attempt, "analysis") else self.analyze(attempt)
        
        # Score doughnut
        score_data = {
            "labels": ["Correct", "Incorrect"],
            "datasets": [{
                "data": [attempt.score, attempt.total_questions - attempt.score],
                "backgroundColor": ["#28a745", "#dc3545"],
            }]
        }
        
        # Topic accuracy bar chart
        all_topics = {}
        answers = UserAnswer.objects.filter(attempt=attempt).select_related("question")
        for ans in answers:
            topic = ans.question.topic or "General"
            if topic not in all_topics:
                all_topics[topic] = {"correct": 0, "total": 0}
            all_topics[topic]["total"] += 1
            if ans.is_correct:
                all_topics[topic]["correct"] += 1
        
        topic_labels = list(all_topics.keys())
        topic_acc = [round(all_topics[t]["correct"] / all_topics[t]["total"] * 100, 1) for t in topic_labels]
        
        topic_data = {
            "labels": topic_labels,
            "datasets": [{
                "label": "Accuracy %",
                "data": topic_acc,
                "backgroundColor": ["#007bff" if a >= 70 else "#ffc107" if a >= 40 else "#dc3545" for a in topic_acc],
            }]
        }
        
        # Difficulty radar
        diff_order = ["easy", "medium", "hard"]
        diff_labels = [d.capitalize() for d in diff_order]
        diff_data_vals = []
        for d in diff_order:
            stats = analysis.difficulty_breakdown.get(d, {"correct": 0, "total": 0})
            acc = round(stats["correct"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0
            diff_data_vals.append(acc)
        
        radar_data = {
            "labels": diff_labels,
            "datasets": [{
                "label": "Accuracy %",
                "data": diff_data_vals,
                "borderColor": "#007bff",
                "backgroundColor": "rgba(0, 123, 255, 0.2)",
            }]
        }
        
        return {
            "score": score_data,
            "topics": topic_data,
            "difficulty": radar_data,
            "weak_topics": analysis.weak_topics,
            "strong_topics": analysis.strong_topics,
        }