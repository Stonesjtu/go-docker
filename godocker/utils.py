import re


STATUS_CREATED = 'created'
STATUS_PENDING = 'pending'
STATUS_RUNNING = 'running'
STATUS_RESCHEDULE = 'reschedule'
STATUS_OVER = 'over'
STATUS_ARCHIVED = 'archived'

STATUS_SECONDARY_SUSPENDED = 'suspended'
STATUS_SECONDARY_SUSPEND_REJECTED = 'suspend rejected'
STATUS_SECONDARY_SUSPEND_REQUESTED = 'suspend requested'
STATUS_SECONDARY_RESUMED = 'resumed'
STATUS_SECONDARY_RESUME_REJECTED = 'resume rejected'
STATUS_SECONDARY_RESUME_REQUESTED = 'suspend requested'
STATUS_SECONDARY_KILLED = 'killed'
STATUS_SECONDARY_KILL_REQUESTED = 'kill requested'
STATUS_SECONDARY_RESCHEDULED = 'rescheduled'
STATUS_SECONDARY_RESCHEDULE_REQUESTED = 'reschedule requested'
STATUS_SECONDARY_SCHEDULER_REJECTED = 'rejected by scheduler'
STATUS_SECONDARY_QUOTA_REACHED = 'quota reached'

QUEUE_QUEUED = 'queued'
QUEUE_RUNNING = 'running'
QUEUE_KILL = 'kill'
QUEUE_SUSPEND = 'suspend'
QUEUE_RESUME = 'resume'

def convert_size_to_int(string_size):
    '''
    Convert a size with unit in long

    :param string_size: size defined with value and unit such as 5k 12M ...
    :type string_size: str
    :return: size value in bytes
    '''
    string_value = 0
    unit_multiplier = 1
    match = re.search("(\d+)([a-zA-Z])", string_size)
    if not match:
        match = re.search("(\d+)", string_size)
        if not match:
            raise ValueError('size pattern not correct: '+str(string_size))
        string_value = int(match.group(1))
    else:
        string_value = int(match.group(1))
        unit = match.group(2).lower()
        if unit == 'k':
            unit_multiplier = 1000
        elif unit == 'm':
            unit_multiplier = 1000 * 1000
        elif unit == 'g':
            unit_multiplier = 1000 * 1000 * 1000
        elif unit == 't':
            unit_multiplier = 1000 * 1000 * 1000 * 1000
        else:
            raise ValueError('wrong unit: '+str(unit))
    return string_value * unit_multiplier

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
