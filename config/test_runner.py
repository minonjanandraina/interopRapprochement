import shutil
import tempfile

from django.conf import settings
from django.test.runner import DiscoverRunner


class TempMediaTestRunner(DiscoverRunner):
    """Redirige MEDIA_ROOT vers un dossier temporaire pendant les tests.

    Sans ca, chaque test qui uploade un fichier (CSV MVOLA, piece jointe d'ecart) l'ecrit
    reellement sous media/ et pollue l'environnement de dev au fil des executions.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._temp_media_dir = tempfile.mkdtemp(prefix='interop_test_media_')
        settings.MEDIA_ROOT = self._temp_media_dir

    def teardown_test_environment(self, **kwargs):
        super().teardown_test_environment(**kwargs)
        shutil.rmtree(self._temp_media_dir, ignore_errors=True)
