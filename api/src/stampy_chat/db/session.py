import time
import logging
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from stampy_chat.env import DB_CONNECTION_URI


logger = logging.getLogger(__name__)

# We create a single engine for the entire application
engine = create_engine(DB_CONNECTION_URI, echo=False)


@contextmanager
def make_session(auto_commit=False):
    with Session(engine, autoflush=False) as session:
        yield session
        if auto_commit:
            session.commit()


class ItemAdder:
    """A helper class to manage adding and flushing items to the database.

    This class exposes an `add(*items)` method which will add any provided items to the
    session, and if needed commit it. It will also handle rollbacks if an error occurs
    while writing.

    Commits happen whenever more than `batch_size` items have been added since the last
    commit, or more than `save_every` seconds have passed - whichever is first.
    """

    def __init__(self, engine=None, batch_size=100, save_every=1):
        """Initialise the adder.

        :param sqlalchemy.Engine engine: The engine to be used for connections. Will create one if not provided
        :param int batch_size: will commit the session once this many items have been added
        :param int save_every: will commit the session if this many seconds have passed since the last addition
        """
        self.engine = engine or create_engine(DB_CONNECTION_URI, echo=False)
        self.batch_size = batch_size
        self.save_every = save_every

        self.session = Session(self.engine)
        self._counter = 0
        self._last_save = time.time()

    def commit(self):
        try:
            self.session.commit()
        except SQLAlchemyError as e:
            logger.warn('Got error when trying to commit to database: %s', e)
            self.session.rollback()
            raise e
        self._last_save = time.time()

    @contextmanager
    def get_session(self):
        if not self.session:
            logger.info('No session - creating new one')
            self.session = Session(self.engine)

        yield self.session

        if (self._counter % self.batch_size) == 0 or time.time() - self._last_save > self.save_every:
            logger.info('Commiting batch to database')
            self.commit()

    def add(self, *items):
        """Add the provided items to the database, commiting them if needed."""
        with self.get_session() as session:
            session.add_all(items)
            self._counter += len(items)
        logger.debug('added %s items', len(items))

    def __del__(self):
        logger.debug('cleaning up session')
        if self.session:
            self.commit()
            self.session.close()