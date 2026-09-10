from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    email = models.EmailField('adresse email', unique=True)
    is_email_verified = models.BooleanField('email verifie', default=False)

    def __str__(self):
        return self.get_username()
