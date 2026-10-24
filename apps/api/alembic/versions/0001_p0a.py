"""Initial CorpusFlow schema.

The first shipped migration contains the P0 business loop so a disposable
database can be upgraded and downgraded as one coherent unit.
"""

from alembic import op
from corpusflow.db.models import (  # noqa: F401
    Asset,
    AssetBlob,
    AuditEvent,
    BuildInput,
    CandidateSample,
    Dataset,
    DatasetBuild,
    DatasetVersion,
    DatasetVersionSample,
    DiscoveryCandidate,
    Document,
    DocumentVersion,
    IngestBatch,
    IngestItem,
    LicenseEvidence,
    LicenseGrant,
    LineageEdge,
    Membership,
    NodeRun,
    PipelineRun,
    PipelineTemplate,
    PipelineVersion,
    ProcessingBatch,
    QualityIssue,
    QualityReview,
    SampleEvidence,
    SampleReview,
    Segment,
    Source,
    UploadSession,
    User,
    Workspace,
)
from corpusflow.db.session import Base

revision = "0001_p0a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
