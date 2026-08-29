from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        STORE_MANAGER = "STORE_MANAGER", "Store Manager"
        DELIVERY_PERSON = "DELIVERY_PERSON", "Delivery Person"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
    )

class DeliveryPerson(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="delivery_profile",
    )
    pending_task_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.user.username
