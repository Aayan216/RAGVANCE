from django.urls import path
from backend import views

urlpatterns = [
    path("", views.upload_view, name="upload"),
    path("process/<int:doc_id>/", views.process_document_view, name="process_document"),
    path("delete/<int:doc_id>/", views.delete_document_view, name="delete_document"),
    path("tutor/", views.tutor_view, name="tutor"),
    path("tutor/ask/", views.tutor_ask_view, name="tutor_ask"),
    path("practice/", views.practice_view, name="practice"),
    path("practice/generate/", views.practice_generate_view, name="practice_generate"),
    path("practice/submit/", views.practice_submit_view, name="practice_submit"),
    path("mock-test/", views.mock_test_settings_view, name="mock_test_settings"),
    path("mock-test/start/", views.mock_test_start_view, name="mock_test_start"),
    path("mock-test/terminate/", views.mock_test_terminate_view, name="mock_test_terminate"),
    path("mock-test/terminated/", views.mock_test_terminated_view, name="mock_test_terminated"),
    path("mock-test/<int:test_id>/", views.mock_test_take_view, name="mock_test_take"),
    path("mock-test/<int:test_id>/submit/", views.mock_test_submit_view, name="mock_test_submit"),
    path("mock-test/<int:attempt_id>/result/", views.mock_test_result_view, name="mock_test_result"),
    path("mock-test/<int:attempt_id>/analysis/", views.mock_test_analysis_view, name="mock_test_analysis"),
    path("mock-test/<int:attempt_id>/review/", views.mock_test_review_view, name="mock_test_review"),
]