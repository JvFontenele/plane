from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0122_alter_draftissue_assignees_alter_issue_assignees_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='estimate',
            name='type',
            field=models.CharField(choices=[('categories', 'Categories'), ('points', 'Points'), ('time', 'Time')], default='categories', max_length=255),
        ),
    ]
