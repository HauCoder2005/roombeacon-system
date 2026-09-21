import sys
from unittest.mock import MagicMock

class MockAirflowExceptions:
    class AirflowException(Exception): pass
    class AirflowSkipException(Exception): pass

class MockAirflowSDK:
    @staticmethod
    def task(*args, **kwargs): 
        def decorator(f):
            mock_task = MagicMock()
            mock_task.expand = MagicMock()
            mock_task.function = f
            return mock_task
        return decorator
        
    @staticmethod
    def dag(*args, **kwargs): 
        def decorator(f):
            return MagicMock()
        return decorator
        
    class Param:
        def __init__(self, *args, **kwargs): pass
        
    class Variable:
        @staticmethod
        def get(*args, **kwargs): return "false"

class MockAirflowTaskTriggerRule:
    class TriggerRule: 
        ALL_DONE = "all_done"

sys.modules['airflow.exceptions'] = MockAirflowExceptions
sys.modules['airflow.sdk'] = MockAirflowSDK
sys.modules['airflow.task'] = MagicMock()
sys.modules['airflow.task.trigger_rule'] = MockAirflowTaskTriggerRule
