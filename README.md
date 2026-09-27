# RAGVANCE - AI Study Assistant

An AI-powered study assistant with RAG (Retrieval-Augmented Generation) capabilities.

## Features
- **Upload** PDF, DOCX, PPTX, TXT files
- **Tutor Mode** - Ask questions, get answers with citations
- **Practice Mode** - Generate and answer MCQs
- **Mock Test** - Timed exams with performance analysis

## Tech Stack
- Django 5.x
- LangChain + Google Gemini
- Sentence Transformers + FAISS
- Bootstrap 5 + Chart.js

## Setup
```bash
uv sync
python manage.py migrate
python manage.py runserver
```