from django.shortcuts import get_object_or_404
from .models import DeliveryTask, TaskStateTransition
from accounts.models import DeliveryPerson
from django.core.exceptions import ValidationError
from django.db import transaction

class DeliveryTaskService:
    @staticmethod
    def create_task(*, title, priority, created_by):
        # Task creation and it's transition should happen simultaneouly OR both fails,
        # so wrapping them up in a transaction
        with transaction.atomic():
            task = DeliveryTask.objects.create(
                title=title,
                priority=priority,
                created_by=created_by,
            )
            # adding the state transition of this task
            TaskStateTransition.objects.create(
                task=task,
                from_state=None,
                to_state=DeliveryTask.State.NEW,
                action=TaskStateTransition.Action.CREATED,
                actor=created_by,

            )
            return task

    @staticmethod
    def get_top_task():
        # Only return the NEWly created top priority task, but based on date descending
        return (
            DeliveryTask.objects.filter(current_state=DeliveryTask.State.NEW)
            .order_by("-priority", "created_at", "id")
            .first()
        )

    @staticmethod
    def accept_task(*, task_id, delivery_user):
        '''
            During a transaction, we chose to lock the order from DeliveryPerson -> Task as per our design.
            1. So, we find and lock the delivery person's profile
            2. Check their capacity
            3. Find and lock the task
            4. Check if the task is NEW
            5. Change the task: NEW -> ACCEPTED and assigned_to = DeliveryPerson and Save them
            6. Increment person's task pending count and save
            7. Perform State transition
        '''
        with transaction.atomic():
            # 1. Find and lock the delivery person
            try:
                delivery_person = (
                    DeliveryPerson.objects.select_for_update().get(user=delivery_user)
                )
            except DeliveryPerson.DoesNotExist:
                raise get_object_or_404(DeliveryPerson, user=delivery_user)


            # 2. Check capacity
            if delivery_person.pending_task_count >= 3:
                raise ValidationError("This Delivery Person already has 3 pending tasks")

            # 3. Find and lock the task
            try:
                task = (
                    DeliveryTask.objects.select_for_update().get(pk=task_id)
                )
            except DeliveryTask.DoesNotExist:
                raise ValidationError("The  Delivery Task does not exist")

            # 4. Validate the state of the task to be only NEW
            if task.current_state != DeliveryTask.State.NEW:
                raise ValidationError("Only a NEW task can be accepted")

            # 5. Update state and save
            task.current_state = DeliveryTask.State.ACCEPTED
            task.assigned_to = delivery_user
            task.save(
                update_fields=["current_state", "assigned_to"]
            )

            # 6. Increment counter
            delivery_person.pending_task_count += 1
            delivery_person.save(update_fields=["pending_task_count"])

            # 7. State Transition
            TaskStateTransition.objects.create(
                task=task,
                from_state=DeliveryTask.State.NEW,
                to_state=DeliveryTask.State.ACCEPTED,
                action=TaskStateTransition.Action.ACCEPTED,
                actor=delivery_user,
            )

            return task


    @staticmethod
    def decline_task(*, task_id, delivery_user):
        '''
            1. Lock Delivery Person and then lock Task in the order
            2. Check if task is ACCEPTED
            3. Check if task is assigned_to this person
            4. Update task state from ACCEPTED to NEW and save them
            5. decrement pending_task_count by 1 and save
            6. Perform State transition
        '''
        with transaction.atomic():
            # 1. Lock Delivery person and then Task
            try:
                delivery_person = (
                    DeliveryPerson.objects.select_for_update().get(user=delivery_user)
                )
            except DeliveryPerson.DoesNotExist:
                raise get_object_or_404(DeliveryPerson, user=delivery_user)

            try:
                task = (
                    DeliveryTask.objects.select_for_update().get(pk=task_id)
                )
            except DeliveryTask.DoesNotExist:
                raise ValidationError("The  Delivery Task does not exist")

            # 2. check task is accepted
            if task.current_state != DeliveryTask.State.ACCEPTED:
                raise ValidationError("Task is not ACCEPTED yet")

            # 3. check if task is assigned to this person
            if task.assigned_to_id != delivery_person.id:
                raise ValidationError("Task is not assigned to this person and so they cannot Decline it")

            # 4. On Decline task changes state from ACCEPTED to NEW
            task.current_state = DeliveryTask.State.NEW
            task.assigned_to = None
            task.save(update_fields=["current_state", "assigned_to"])

            # 5. decrement pending task count of the delivery person
            delivery_person.pending_task_count -= 1
            delivery_person.save(update_fields=["pending_task_count"])

            # 6. State Transition
            TaskStateTransition.objects.create(
                task=task,
                from_state=DeliveryTask.State.ACCEPTED,
                to_state=DeliveryTask.State.NEW,
                action=TaskStateTransition.Action.DECLINED,
                actor=delivery_person,
            )

            return task


    @staticmethod
    def complete_task(*, task_id, delivery_user):
        '''
            same as decline_task() just we need to make the task state from ACCEPTED to COMPLETED
        '''
        with transaction.atomic():
            # 1. Lock Delivery person and then Task
            try:
                delivery_person = (
                    DeliveryPerson.objects.select_for_update().get(user=delivery_user)
                )
            except DeliveryPerson.DoesNotExist:
                raise get_object_or_404(DeliveryPerson, user=delivery_user)

            try:
                task = (
                    DeliveryTask.objects.select_for_update().get(pk=task_id)
                )
            except DeliveryTask.DoesNotExist:
                raise ValidationError("The  Delivery Task does not exist")

            # 2. check task is accepted
            if task.current_state != DeliveryTask.State.ACCEPTED:
                raise ValidationError("Task is not ACCEPTED yet")

            # 3. check if task is assigned to this person
            if task.assigned_to_id != delivery_person.id:
                raise ValidationError("Task is not assigned to this person and so they cannot Decline it")

            # 4. Task changes state from ACCEPTED to COMPLETED
            task.current_state = DeliveryTask.State.COMPLETED
            task.save(update_fields=["current_state"])

            # 5. decrement pending task count of the delivery person
            delivery_person.pending_task_count -= 1
            delivery_person.save(update_fields=["pending_task_count"])

            # 6. State Transition
            TaskStateTransition.objects.create(
                task=task,
                from_state=DeliveryTask.State.ACCEPTED,
                to_state=DeliveryTask.State.NEW,
                action=TaskStateTransition.Action.DECLINED,
                actor=delivery_person,
            )

            return task


    @staticmethod
    def cancel_task(*, task_id, store_manager):
        '''
            1. Validate the task
            2. Only a NEW task can be cancelled. This needs to be validated
            3. Validate that only the store manager who created it can cancel the task
            4. Update state of task to CANCELLED and save
            5. Perform State transition
        '''
        with transaction.atomic():
            try:
                task = (
                    DeliveryTask.objects.select_for_update().get(pk=task_id)
                )
            except DeliveryTask.DoesNotExist:
                raise ValidationError("The  Delivery Task does not exist")

            if task.current_state != DeliveryTask.State.NEW:
                raise ValidationError("Task is not NEW and so cannot be cancelled")

            if task.created_by_id != store_manager.id:
                raise ValidationError(
                    "Task is not assigned to this Store manager and so they cannot cancel it"
                )

            task.current_state = DeliveryTask.State.CANCELLED
            task.save(update_fields=["current_state"])

            TaskStateTransition.objects.create(
                task=task,
                from_state=DeliveryTask.State.NEW,
                to_state=DeliveryTask.State.CANCELLED,
                action=TaskStateTransition.Action.CANCELLED,
                actor=store_manager,
            )

            return task





