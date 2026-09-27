from django.db import models


class Document(models.Model):
    FILE_TYPES = [
        ("pdf", "PDF"),
        ("docx", "DOCX"),
        ("pptx", "PPTX"),
        ("txt", "TXT"),
    ]
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/")
    file_type = models.CharField(max_length=10, choices=FILE_TYPES)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    chunk_count = models.IntegerField(default=0)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title


class Chunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    content = models.TextField()
    embedding_id = models.IntegerField()
    page_number = models.IntegerField(null=True, blank=True)
    chunk_index = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "chunk_index"]

    def __str__(self):
        return f"{self.document.title} - Chunk {self.chunk_index}"


class MockTest(models.Model):
    DIFFICULTY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]
    QUESTION_COUNTS = [(10, "10"), (20, "20"), (30, "30"), (50, "50")]
    STATUS_CHOICES = [
        ("created", "Created"),
        ("active", "Active"),
        ("completed", "Completed"),
        ("terminated", "Terminated"),
    ]

    num_questions = models.IntegerField(choices=QUESTION_COUNTS, default=20)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default="medium")
    timer_minutes = models.IntegerField(default=30)
    doc_ids = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Mock Test {self.id} - {self.num_questions}Q {self.difficulty}"


class TestQuestion(models.Model):
    QUESTION_TYPE_CHOICES = [
        ("mcq", "MCQ"),
        ("true_false", "True/False"),
    ]

    test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name="questions")
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default="mcq")
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    correct_answer = models.CharField(max_length=1, choices=[("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")])
    difficulty = models.CharField(max_length=10, choices=MockTest.DIFFICULTY_CHOICES)
    topic = models.CharField(max_length=200, blank=True)
    explanation = models.TextField(blank=True)
    source_chunk_ids = models.JSONField(default=list)

    def __str__(self):
        return f"Q{self.id}: {self.question_text[:50]}"


class TestAttempt(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("completed", "Completed"),
        ("terminated", "Terminated"),
    ]

    test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name="attempts")
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.IntegerField(default=0)
    total_questions = models.IntegerField()
    percentage = models.FloatField(default=0.0)
    time_taken_seconds = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Attempt {self.id} - {self.percentage:.1f}%"


class UserAnswer(models.Model):
    attempt = models.ForeignKey(TestAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(TestQuestion, on_delete=models.CASCADE)
    selected_option = models.CharField(max_length=1, choices=[("A", "A"), ("B", "B"), ("C", "C"), ("D", "D")])
    is_correct = models.BooleanField()
    answered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.question} - {self.selected_option} ({'✓' if self.is_correct else '✗'})"


class PerformanceAnalysis(models.Model):
    attempt = models.OneToOneField(TestAttempt, on_delete=models.CASCADE, related_name="analysis")
    weak_topics = models.JSONField(default=list)
    strong_topics = models.JSONField(default=list)
    difficulty_breakdown = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Analysis for Attempt {self.attempt.id}"