from rest_framework import serializers
from .models import DeliveryTask, TaskStateTransition

class CreateTaskSerializer(serializers.Serializer):
    title = serializers.CharField(required=True, max_length=225)
    priority = serializers.ChoiceField(
        choices=["high", "medium", "low"], required=True
    )

    def validate_priority(self, value):
        priority_mapping = {
            "high": DeliveryTask.Priority.HIGH,
            "medium": DeliveryTask.Priority.MEDIUM,
            "low": DeliveryTask.Priority.LOW,
        }
        return priority_mapping[value]

class DeliveryTaskSerializer(serializers.ModelSerializer):
    priority = serializers.CharField(
        source="get_priority_display",
        read_only=True,
    )
    class Meta:
        model = DeliveryTask
        fields = ["id", "title", "priority", "created_at", "created_by", "current_state", "assigned_to"]

class TaskStateTransitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskStateTransition
        fields = ["id", "task", "from_state", "to_state", "action", "actor", "timestamp"]
