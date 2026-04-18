from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_ownerinfo'),
    ]

    operations = [
        migrations.DeleteModel(
            name='SpecificPartInfo',
        ),
    ]
