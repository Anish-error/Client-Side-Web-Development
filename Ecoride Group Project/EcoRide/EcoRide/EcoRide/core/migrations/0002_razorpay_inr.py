from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="payment",
            old_name="stripe_session_id",
            new_name="gateway_order_id",
        ),
        migrations.RenameField(
            model_name="payment",
            old_name="stripe_payment_intent_id",
            new_name="gateway_payment_id",
        ),
        migrations.RenameField(
            model_name="rental",
            old_name="amount_cents",
            new_name="amount_minor_units",
        ),
        migrations.RenameField(
            model_name="payment",
            old_name="amount_cents",
            new_name="amount_minor_units",
        ),
        migrations.AlterField(
            model_name="rental",
            name="amount_minor_units",
            field=models.PositiveIntegerField(default=5000),
        ),
        migrations.AlterField(
            model_name="payment",
            name="amount_minor_units",
            field=models.PositiveIntegerField(default=5000),
        ),
        migrations.AddField(
            model_name="rental",
            name="currency",
            field=models.CharField(default="INR", max_length=3),
        ),
        migrations.AddField(
            model_name="payment",
            name="currency",
            field=models.CharField(default="INR", max_length=3),
        ),
    ]
