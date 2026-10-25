import time

from corpusflow.core.config import load_settings
from corpusflow.db.session import build_engine
from corpusflow.worker.celery_app import celery_app
from corpusflow.worker.outbox import publish_pending
from sqlalchemy.orm import sessionmaker

settings = load_settings()
factory = sessionmaker(build_engine(settings), expire_on_commit=False)


class Dispatcher:
    def publish(self, event) -> object:
        task_name = {
            "pipeline.run.execute": "corpusflow.execute_pipeline_run",
            "collection.plan.execute": "corpusflow.collect",
            "rag.answer.generate": "corpusflow.generate",
            "rag.index.build": "corpusflow.rag_job",
            "rag.evaluation.execute": "corpusflow.rag_job",
            "dataset.version.deliver": "corpusflow.deliver_dataset_version",
        }.get(event.event_type)
        if not task_name:
            raise ValueError(f"unsupported outbox event: {event.event_type}")
        aggregate_id = str(
            event.payload.get("run_id", event.payload.get("dataset_version_id", event.aggregate_id))
        )
        return celery_app.send_task(task_name, args=[aggregate_id])


while True:
    with factory() as session:
        publish_pending(session, Dispatcher())
    time.sleep(1)
