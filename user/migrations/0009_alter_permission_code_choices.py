# Migration to update Permission.code choices to include CONSULTER_RAPPROCHEMENT

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0008_add_consulter_rapprochement_to_vue_only_roles'),
    ]

    operations = [
        migrations.AlterField(
            model_name='permission',
            name='code',
            field=models.CharField(choices=[('importer_csv_mvola', 'Importer un fichier CSV MVOLA'), ('importer_fichier_om', 'Importer un fichier Orange Money'), ('lancer_rapprochement', 'Lancer un rapprochement'), ('consulter_rapprochement', 'Consulter les resultats de rapprochement'), ('traiter_ecarts', 'Traiter les ecarts (statut, commentaire, piece jointe, rollback, ticket Aspekt)'), ('gerer_roles', 'Gerer les roles et privileges'), ('gerer_utilisateurs', 'Gerer les utilisateurs (assignation de roles)'), ('vue_only', 'Consultation seule')], max_length=50, unique=True),
        ),
    ]
