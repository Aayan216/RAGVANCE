from django import forms
from core.models import Document


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "file"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Document title (optional)"}),
            "file": forms.FileInput(attrs={"class": "form-control", "accept": ".pdf,.docx,.pptx,.txt"}),
        }

    def clean_file(self):
        file = self.cleaned_data["file"]
        allowed_types = ["pdf", "docx", "pptx", "txt"]
        ext = file.name.split(".")[-1].lower()
        if ext not in allowed_types:
            raise forms.ValidationError("Unsupported file type. Allowed: PDF, DOCX, PPTX, TXT")
        return file


class TutorQuestionForm(forms.Form):
    question = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Ask a question about your study materials..."
        }),
        label=""
    )