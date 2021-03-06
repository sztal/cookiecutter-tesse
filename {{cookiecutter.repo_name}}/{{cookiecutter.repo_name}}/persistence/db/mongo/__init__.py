"""*MongoDB* connector based on *pymongo* and *Mongoengine*

See Also
--------
pymongo
mongoengine
"""
import os
import re
import time
import math
from collections import Iterable, Mapping
from pymongo import UpdateOne, UpdateMany
from pymongo.errors import OperationFailure
import mongoengine
from .utils import update_action_hook, query_factory
from .interface import MongoPersistenceInterface
from ....persistence import DBPersistence
from {{ cookiecutter.repo_name }}.base.interface import DBPersistenceInterface
from {{ cookiecutter.repo_name }}.base.interface import DBPersistenceInterface
from {{ cookiecutter.repo_name }}.base.validators import BaseValidator


def init(user, password, host, port, db, authentication_db=None,
         use_envvars=True, handle_double_auth_error=False):
    """Initilize Mongoengine ODM.

    Parameters
    ----------
    user : str
        Username to authenticate with.
    password : str
        User authentication password.
    host : str
        Host IP address/name.
    port : str
        Port number.
    db : str
        Database name.
    authentication_db : str or None
        Authentication databse name.
        Use `db` if `None`.
    handle_double_auth_error : bool
        Should double authentication error be handled.
        Sometimes same user is not logged out properly from previous session
        and thus disables any further operations.
        The hacky way to deal with it is just to force log out when
        an operational error of this kind happends and then log again.
    """
    def connect(uri, authentication_source):
        """Connect to MongoDB."""
        return mongoengine.connect(host=uri, authentication_source=authentication_db)
    mongo_uri = 'mongodb://{username}:{password}@{host}:{port}/{db}'
    if not authentication_db:
        authentication_db = db
    uri = mongo_uri.format(
        username=user,
        password=password,
        host=host,
        port=port,
        db=db
    )
    mongo = connect(uri, authentication_db)
    if handle_double_auth_error:
        pass
        # try:
        #     mongo.database_names()
        # except OperationFailure as exc:
        #     rx = re.compile(
        #         r"Another user is already authenticated to this database",
        #         re.IGNORECASE
        #     )
        #     if rx.search(str(exc)):
        #         mongo.get_database().logout()
        #         mongo = connect(uri, authentication_db)
        # else:
        #     raise exc
    return mongo


class MongoPersistence(DBPersistence):
    """MongoDB persistence class.

    See Also
    --------
    mongoengine
    """
    _interface = MongoPersistenceInterface

    def __init__(self, item_name='document', **kwds):
        """Initialization method.

        Parameters
        ----------
        settings : :py:class:`{{ cookiecutter.repo_name }}.persistence.db.mongo.MongoPersistenceInterface`
            MongoDB persistence settings object.
        item_name : str
            Item name
        **kwds :
            Other arguments passed to
            :py:class:`{{ cookiecutter.repo_name }}.persistence.db.mongo.MongoPersistenceInterface`
            when `settings=None`.
        """
        super().__init__(item_name, **kwds)

    def persist(self, doc, print_num=True, **kwds):
        """Persist documents in MongoDB in batches.

        Parameters
        ----------
        doc : dict-like
            Dict-like object representing a valid MongoDB document.
        print_num : bool
            Should number of processed items be printed.
        **kwds :
            Parameters passed to `update`.
        """
        self.inc(print_num=print_num)
        if hasattr(self.model, 'from_dict'):
            doc = self.model.from_dict(doc, only_dict=True)
        self.queue.appendleft(doc)
        self.do_update(**kwds)

    def finalize(self):
        """Update last batch regardless of the size."""
        self.do_update(min_batch_size=1)

    def make_update_op(self, doc, multiple=None, upsert=None, **kwds):
        """Make :py:module:`pymongo` update op.

        Parameters
        ----------
        doc : Mapping
            Document to update.
        multiple : bool
            Should :py:class:`UpdateOne` or :py:class:`UpdateMany` be used.
        upsert : bool
            Should upsert mode be used instead of update.
        **kwds :
            Other arguments passed to :py:class:`UpdateOne` or :py:class:`UpdateMany`.
        """
        if multiple is None:
            multiple = self.multiple
        if upsert is None:
            upsert = self.upsert
        update_query = self.query(doc)
        update = self.processor(doc)
        if multiple:
            op = UpdateMany(update_query, update, upsert=upsert, **kwds)
        else:
            op = UpdateOne(update_query, update, upsert=upsert, **kwds)
        return op

    def make_bulk_update(self, bulk_write_kwds=None, **kwds):
        """Make bulk update.

        Parameters
        ----------
        bulk_write_kwds : dict or None
            Arguments passed to :py:func:`pymongo.bulk_write`.
            If `None` then `ordered=False` is passed.
        **kwds :
            Other arguments passed to
            :py:meth:`{{ cookiecutter.repo_name }}.persistence.db.mongo.MongoPersistence.make_update.op`.
        """
        if bulk_write_kwds is None:
            bulk_write_kwds = { 'ordered': False }
        bulk_ops = []
        while self.queue:
            op = self.make_update_op(self.queue.pop(), **kwds)
            bulk_ops.append(op)
        if bulk_ops:
            self.model._get_collection().bulk_write(bulk_ops, **bulk_write_kwds)

    def do_update(self, min_batch_size=None, update=None, **kwds):
        """Persist a batch of documents in MongoDB.

        Parameters
        ----------
        min_batch_size : int or None
            Minimal batch size.
            No minimal size if non-positive.
            Use configuration value if `None`.
        update : bool
            Should update mode be used instead of insert.
        **kwds :
            Parameters passed to `make_bulk_update`.

        Returns
        -------
        bool
            True if successful update has been done.
        """
        if update is None:
            update = self.update
        coll_name = self.model._get_collection_name()
        n_docs = len(self.queue)
        # Check if update should be done considering selected batch size
        if min_batch_size is None:
            if not self.batch_size or self.batch_size <= 0:
                min_batch_size = math.inf
            else:
                min_batch_size = self.batch_size
        elif min_batch_size <= 0:
            min_batch_size = math.inf
        if n_docs < min_batch_size:
            return False
        # Perform update
        n_attempts = 1 + self.n_retry
        attempt = 0
        exc = None
        while attempt < n_attempts:
            attempt += 1
            try:
                if not update:
                    docs = [ self.model(**self.queue.pop()) for _ in range(n_docs) ]
                    self.model.objects.insert(docs)
                else:
                    self.make_bulk_update(**kwds)
                exc = None
                break
            except Exception as exc:
                n_left = n_attempts - attempt
                if n_attempts == 1:
                    m = f"Update attempt for collection '{coll_name}' failed."
                elif n_left > 0:
                    m = f"Update attempt no. {attempt} for collection '{coll_name}' failed. Retrying {n_left} times."
                else:
                    m = f"Last update attempt for collection '{coll_name}' (no. {attempt} failed. Stop trying."
                if self.logger:
                    self.logger.exception(m)
        if exc:
            raise exc
        m = f"Updated {n_docs} records in collection '{coll_name}' ({self.count} in total)."
        if self.logger:
            self.logger.info(m)

    def get_model_name(self):
        """Get collection model name."""
        return self.model._get_collection_name()

    def drop_model_data(self, query=None, **kwds):
        """Drop model data.

        Parameters
        ----------
        query : any
            If callable then it is called on self (and `**kwds`)
            and the results is returned.
            If string then it is used as a raw *MongoDB* query.
        **kwds :
            Optional keyword arguments passed to either 'query' or
            'self.clear_model' callable.
        """
        if query is None:
            query = self.clear_model
        if isinstance(query, Mapping):
            _query = query
            query = lambda self: \
                self.model.objects(__raw__=_query).delete()
        super().drop_model_data(query, **kwds)

