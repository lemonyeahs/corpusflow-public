import time

from corpusflow.core.config import load_settings
from corpusflow.db.session import build_engine
from corpusflow.worker.celery_app import celery_app
from corpusflow.worker.outbox import publish_pending
from sqlalchemy.orm import sessionmaker

settings = load_settings()
factory = sessionmaker(build_engine(settings), expire_on_commit=False)


class Dispatcher:
    def delay(self, run_id: str) -> object:
        return celery_app.send_task("corpusflow.execute_pipeline_run", args=[run_id])


while True:
    with factory() as session:
        publish_pending(session, Dispatcher())
    time.sleep(1)
