from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_mocktest_doc_ids_mocktest_status_testattempt_status_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="testquestion",
            name="question_type",
            field=models.CharField(
                choices=[("mcq", "MCQ"), ("true_false", "True/False")],
                default="mcq",
                max_length=20,
            ),
        ),
    ]
