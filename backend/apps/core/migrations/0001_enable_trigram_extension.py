"""Enable PostgreSQL pg_trgm extension for GIN trigram search indexing."""

from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Initial core migration enabling pg_trgm extension."""

    initial = True

    dependencies = []

    operations = [
        TrigramExtension(),
    ]
