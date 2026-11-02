from django.db import migrations, models
import django.db.models.deletion


def assign_default_store(apps, schema_editor):
    """Every product must belong to a store: give orphans a default 'zento' store."""
    Product = apps.get_model('shop', 'Product')
    Store = apps.get_model('shop', 'Store')
    orphans = Product.objects.filter(store__isnull=True)
    if orphans.exists():
        store, _ = Store.objects.get_or_create(slug='zento', defaults={'name': 'Zento'})
        orphans.update(store=store)


class Migration(migrations.Migration):

    dependencies = [
        ('shop', '0002_stores'),
    ]

    operations = [
        migrations.AddField(
            model_name='store',
            name='verified',
            field=models.BooleanField(default=False, help_text='Show the blue check next to the username'),
        ),
        migrations.AlterField(
            model_name='product',
            name='pinned',
            field=models.BooleanField(default=False, help_text='Pinned products appear in the main feed and first on the store page'),
        ),
        migrations.AddField(
            model_name='story',
            name='store',
            field=models.ForeignKey(blank=True, help_text='Store whose avatar and name are shown on the story ring', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='stories', to='shop.store'),
        ),
        migrations.CreateModel(
            name='ProductImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='products/')),
                ('position', models.PositiveIntegerField(default=0)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='photos', to='shop.product')),
            ],
            options={
                'ordering': ['position', 'id'],
            },
        ),
        migrations.RunPython(assign_default_store, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='product',
            name='store',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='products', to='shop.store'),
        ),
    ]
