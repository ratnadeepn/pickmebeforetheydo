from django.conf import settings
from django.db import models

class DeliveryTask(models.Model):
    class Priority(models.IntegerChoices):
        LOW = 1, "Low"
        MEDIUM = 2, "Medium"
        HIGH = 3, "High"

    class State(models.TextChoices):
        NEW = "NEW", "New"
        ACCEPTED = "ACCEPTED", "Accepted"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    title = models.CharField(max_length=255)
    priority = models.PositiveIntegerField(choices=Priority.choices, default=Priority.LOW)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,
                                   on_delete=models.PROTECT,
                                   related_name="created_delivery_tasks")
    current_state = models.CharField(choices=State.choices, default=State.NEW)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL,
                                    on_delete=models.PROTECT,
                                    related_name="assigned_delivery_tasks",
                                    null=True,
                                    blank=True)
    def __str__(self):
        return self.title

    class Meta:
        indexes = [
            models.Index(fields=["current_state", "priority", "created_at"]),
        ]

class TaskStateTransition(models.Model):
    class Action(models.TextChoices):
        CREATED = "CREATED", "Created"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    task = models.ForeignKey(DeliveryTask, on_delete=models.CASCADE, related_name="transitions")
    from_state = models.CharField(choices=DeliveryTask.State.choices,
                                  null=True, blank=True, max_length=20)
    to_state = models.CharField(choices=DeliveryTask.State.choices, max_length=20)
    action = models.CharField(choices=Action.choices, max_length=20)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,
                              on_delete=models.PROTECT,
                              related_name="task_transitions")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp", "id"]




