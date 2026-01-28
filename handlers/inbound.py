from sqlalchemy.orm import Session
from models.work_item import WorkItem

def handle_process_inbound(db: Session, wi: WorkItem) -> None:
    """
    - load session
    - reduce state
    - emit new outbox rows
    """

    print(f"Processing inbound work: {wi.work_id}, {wi.kind}")
    pass
