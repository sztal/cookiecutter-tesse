"""Custom *Taskiss-Celery* task classes and decorators."""
from collections import defaultdict, Mapping
from logging import getLogger
from celery import Task
from celery.worker.request import Request
from .utils import merge_results
from .exceptions import BadTaskArgumentsError
from .validators import TaskissValidator


class TaskissRequest(Request):
    """*Taskiss* request class."""
    pass


class TaskissTask(Task):
    """*Taskiss* task class.

    This is an extension of the base :py:class:`celery.Task` class
    that restructures incoming arguments to comply to the task
    main function signature.
    """
    _interface = None
    Request = TaskissRequest
    logger = getLogger('taskiss')

    def __call__(self, *args, args_to_kwds=True, raise_ambiguous_args=True, **kwds):
        """Task call method.

        Parameters
        ----------
        *args :
            Positional arguments passed to the main task function.
        args_to_kwds : bool
            Should positional arguments be merged with kwds.
        raise_ambiguous_args : bool
            Should error be raised with ambiguous arguments are passed.
            If `False` then ambiguous args are overwritten.
        **kwds :
            Keyword arguments passed to the main task function.
        """
        if '_args' in kwds:
            args = [ *args, *kwds['_args'] ]
        if args_to_kwds and args:
            args = merge_results(args, raise_ambiguous_args=raise_ambiguous_args)
            kwds = { **kwds, **args }
        task_name_kwds = kwds.pop(self.name, {})
        kwds = { **kwds, **task_name_kwds }
        call_kwds = self.interface.validated(kwds)
        if call_kwds is None:
            raise BadTaskArgumentsError(self.interface.errors)
        res = super().__call__(**call_kwds)
        kwds = { k: v for k, v in kwds.items() if k not in call_kwds }
        if isinstance(res, Mapping):
            kwds = { **kwds, **res }
        else:
            args = [ *args, res ]
        return self.make_results(*args, **kwds)

    @property
    def interface(self):
        """Interface getter."""
        if self._interface is None:
            cn = self.__class__.__name__
            raise AttributeError(f"'{cn}' does not define interface")
        elif isinstance(self._interface, Mapping):
            self._interface = TaskissValidator(self._interface)
        return self._interface

    def make_results(self, *args, **kwds):
        """Organize results in the standard _Taskiss_ format.

        Notes
        -----
        Since order of task execution is not guaranteed in *Celery*
        the *Taskiss* communication protocol uses key-value pairs
        only represented as dictionaries with default value of `None`.

        If positional arguments are passed, then they are assigned
        to the same name as the task name.
        However, usage of positional arguments is highly discouraged.

        Parameters
        ----------
        *args :
            Positional arguments.
        **kwds :
            Keyword arguments.
        """
        res = defaultdict(lambda: None, **kwds)
        if args:
            res['_args'] = args
        return res
