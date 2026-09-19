from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

import task.permissions
from .permissions import IsStoreManager, IsDeliveryPerson
from .serializers import (
    CreateTaskSerializer,
    DeliveryTaskSerializer,
    TaskStateTransitionSerializer
)

from .services import DeliveryTaskService
from .models import DeliveryTask, TaskStateTransition

class StoreManagerTaskListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsStoreManager]

    def post(self, request):
        input_serializer = CreateTaskSerializer(data=request.data)
        input_serializer.is_valid(
            raise_exception=True
        )
        try:
            task = DeliveryTaskService.create_task(
                title=input_serializer.validated_data['title'],
                priority=input_serializer.validated_data['priority'],
                created_by=request.user,
            )

        except ValidationError as e:
            return Response(
                {"detail": e.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        output_serializer = DeliveryTaskSerializer(task)

        return Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    def get(self, request):
        tasks = (
            DeliveryTask.objects
            .filter(created_by=request.user)
            .order_by('-created_at')
        )

        serializer = DeliveryTaskSerializer(tasks, many=True)
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

class StoreManagerTaskHistoryView(APIView):
    permission_classes = [IsAuthenticated, IsStoreManager]

    def get(self, request, task_id):
        try:
            tasks = DeliveryTask.objects.get(
                id = task_id,
                created_by=request.user,
            )
        except DeliveryTask.DoesNotExist:
            return Response(
                {"detail": "Task not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        transitions = (
            TaskStateTransition.objects
            .filter(task=task)
            .order_by('timestamp', 'id')
        )

        serializer = TaskStateTransitionSerializer(transitions, many=True)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

class StoreManagerTaskCancelView(APIView):
    permission_classes = [IsAuthenticated, IsStoreManager]

    def post(self, request, task_id):

        get_object_or_404(DeliveryTask, id=task_id, created_by=request.user)

        try:
            task = DeliveryTaskService.cancel_task(task_id=task_id,
                                                   store_manager=request.user)
        except ValidationError as e:
            return Response(
                {"detail": e.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DeliveryTaskSerializer(task)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

class DeliveryTopTaskView(APIView):
    permission_classes = [IsAuthenticated, IsDeliveryPerson]

    def get(self, request):
        task = DeliveryTaskService.get_top_task()

        if not task:
            return Response(
                status=status.HTTP_204_NO_CONTENT,
            )
        serializer = DeliveryTaskSerializer(task)
        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )




