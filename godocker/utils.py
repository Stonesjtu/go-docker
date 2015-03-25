

STATUS_PENDING = 'pending'
STATUS_RUNNING = 'running'
STATUS_RESCHEDULE = 'reschedule'
STATUS_OVER = 'over'

STATUS_SECONDARY_SUSPENDED = 'suspended'
STATUS_SECONDARY_SUSPEND_REJECTED = 'suspend rejected'
STATUS_SECONDARY_SUSPEND_REQUESTED = 'suspend requested'
STATUS_SECONDARY_RESUMED = 'resumed'
STATUS_SECONDARY_RESUME_REJECTED = 'resume rejected'
STATUS_SECONDARY_RESUME_REQUESTED = 'suspend requested'
STATUS_SECONDARY_KILLED = 'killed'
STATUS_SECONDARY_KILL_REQUESTED = 'kill requested'

QUEUE_QUEUED = 'queued'
QUEUE_RUNNING = 'running'
QUEUE_KILL = 'kill'
QUEUE_SUSPEND = 'suspend'
QUEUE_RESUME = 'resume'

def is_array_task(task):
    '''
    Checks if input task is an array task eg a parent task

    :return: bool
    '''
    if 'array' in task['requirements']:
        if 'values' in task['requirements']['array'] and task['requirements']['array']['values']:
            return True
        else:
            return False

    else:
        return False

def is_array_child_task(task):
    '''
    Checks if input task is an array child task

    :return: bool
    '''
    if 'parent_task_id' in task and task['parent_task_id']:
        return True
    return False
