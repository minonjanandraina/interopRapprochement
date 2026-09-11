"""Catalogue fixe des privileges (actions metier) pouvant etre accordes a un role.

Cf. CLAUDE.md - Sprint 6, roles dynamiques. Le code d'un privilege est utilise en dur dans les
vues (cf. user.decorators.privilege_required) : ce n'est pas une liste ouverte a la creation par
l'utilisateur, seule leur repartition entre roles est dynamique.
"""

IMPORTER_CSV_MVOLA = 'importer_csv_mvola'
LANCER_RAPPROCHEMENT = 'lancer_rapprochement'
TRAITER_ECARTS = 'traiter_ecarts'
GERER_ROLES = 'gerer_roles'
GERER_UTILISATEURS = 'gerer_utilisateurs'

PRIVILEGE_CHOICES = [
    (IMPORTER_CSV_MVOLA, 'Importer un fichier CSV MVOLA'),
    (LANCER_RAPPROCHEMENT, 'Lancer un rapprochement'),
    (TRAITER_ECARTS, 'Traiter les ecarts (statut, commentaire, piece jointe, rollback, ticket Aspekt)'),
    (GERER_ROLES, 'Gerer les roles et privileges'),
    (GERER_UTILISATEURS, 'Gerer les utilisateurs (assignation de roles)'),
]
