"""Protect consumed call reservations and terminal answers against rewriting."""

from alembic import op

revision = "0017_generation_guards"
down_revision = "0016_evidence_generation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TRIGGER generation_immutable ON generation_runs")
    op.execute("""CREATE FUNCTION cf_generation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' OR OLD.status IN ('succeeded','failed','refused') OR
           (OLD.call_reserved AND NOT NEW.call_reserved) OR
           NEW.config_snapshot IS DISTINCT FROM OLD.config_snapshot OR
           NEW.trace_id IS DISTINCT FROM OLD.trace_id OR
           NEW.workspace_id IS DISTINCT FROM OLD.workspace_id OR
           NEW.created_by IS DISTINCT FROM OLD.created_by THEN
          RAISE EXCEPTION 'generation reservation and result are immutable';
        END IF;
        RETURN NEW;
      END $$;""")
    op.execute(
        "CREATE TRIGGER generation_immutable BEFORE UPDATE OR DELETE ON generation_runs "
        "FOR EACH ROW EXECUTE FUNCTION cf_generation_guard()"
    )


def downgrade():
    op.execute("DROP TRIGGER generation_immutable ON generation_runs")
    op.execute("DROP FUNCTION cf_generation_guard()")
    op.execute(
        "CREATE TRIGGER generation_immutable BEFORE UPDATE OR DELETE ON generation_runs "
        "FOR EACH ROW EXECUTE FUNCTION cf_rag_completed_immutable()"
    )
