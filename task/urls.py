from django.urls import path
from .views import (
    StoreManagerTaskListCreateView,
    StoreManagerTaskHistoryView,
    StoreManagerTaskCancelView,
    DeliveryTopTaskView
)

app_name = 'task'

urlpatterns = [
    path(
        "tasks/",
        StoreManagerTaskListCreateView.as_view(),
        name="manager-task-list-create",
    ),

    path(
        "tasks/<int:task_id>/history/",
        StoreManagerTaskHistoryView.as_view(),
        name="manager-task-history",
    ),
    path(
        "tasks/<int:task_id>/cancel/",
        StoreManagerTaskCancelView.as_view(),
        name="manager-task-cancel",
    ),
    path(
        "delivery/top-task/",
        DeliveryTopTaskView.as_view(),
        name="delivery-top-task",
    ),

]