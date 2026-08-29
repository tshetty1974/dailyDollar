"""
Run-level checkpointing: never pay twice for work already done.

A multi-stock run is long and expensive -- five analysts plus a
three-turn debate for every candidate. If it dies on the third ticker,
restarting from scratch would repeat two complete orchestrations.

The framework's own workflow checkpoints (see `build_workflow`) can
resume a single stock's orchestration, but they know nothing about the
loop around it. This module covers that outer layer: it records each
candidate's findings as they complete, so a resumed run skips straight
past the stocks that are already done.

The run is identified by a fingerprint of the request itself, so simply
re-running the same command resumes it -- there is no run id for the
user to keep track of.
"""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

from models import InvestmentRequest, PortfolioRecommendation


CHECKPOINT_DIR = Path("data/checkpoints")


class RunCheckpoint(BaseModel):
    """Partial state of an in-flight analysis run."""

    run_id: str

    request: InvestmentRequest

    # ticker -> section name -> texts. Mirrors `all_findings` in the
    # orchestrator, including the debate transcript once it exists.
    findings: dict[str, dict[str, list[str]]] = Field(default_factory=dict)

    # The pre-debate draft, kept so a resume does not have to redo the
    # most expensive single call in the pipeline.
    pre_debate: PortfolioRecommendation | None = None

    def has_research(self, ticker: str) -> bool:
        """True when this candidate's specialist research is done."""

        return bool(self.findings.get(ticker))

    def has_debate(self, ticker: str, debate_key: str) -> bool:
        """True when this candidate has already been debated."""

        return bool(self.findings.get(ticker, {}).get(debate_key))

    def progress(self, debate_key: str) -> str:
        """A short human-readable summary of what is already done."""

        if not self.findings:
            return "nothing completed yet"

        parts = []

        for ticker, sections in self.findings.items():

            stage = "researched"

            if sections.get(debate_key):
                stage = "researched + debated"

            parts.append(f"{ticker} ({stage})")

        return ", ".join(parts)


def run_id_for(request: InvestmentRequest) -> str:
    """
    Fingerprint a request so the same command resumes the same run.

    Derived from the request rather than generated, so the user never
    has to pass a run id. Changing any part of the objective -- the
    amount, the risk appetite, the candidates -- produces a different
    id, which is correct: that is a different analysis, not a resume.
    """

    payload = json.dumps(
        {
            "user_id": request.user_id,
            "tickers": sorted(request.tickers),
            "amount": request.amount,
            "risk_appetite": request.risk_appetite.value,
            "horizon": request.horizon.value,
            "constraints": sorted(request.constraints),
        },
        sort_keys=True,
    )

    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def checkpoint_path(run_id: str) -> Path:
    """Where this run's checkpoint lives."""

    return CHECKPOINT_DIR / f"{run_id}.json"


def load_checkpoint(request: InvestmentRequest) -> RunCheckpoint:
    """
    Load any partial state for this request.

    A missing or unreadable checkpoint yields a fresh one rather than an
    error. The worst case is repeating work, which is exactly what would
    have happened without checkpointing at all -- a damaged checkpoint
    must never be able to block a run.
    """

    run_id = run_id_for(request)

    path = checkpoint_path(run_id)

    if not path.exists():
        return RunCheckpoint(run_id=run_id, request=request)

    try:
        return RunCheckpoint.model_validate_json(path.read_text())

    except Exception as error:

        print(f">>> WARNING: could not read checkpoint {run_id}: {error}")
        print(">>> starting this run from scratch")

        return RunCheckpoint(run_id=run_id, request=request)


def save_checkpoint(checkpoint: RunCheckpoint) -> None:
    """
    Persist partial state.

    Written to a temporary file and renamed into place: an interruption
    during the write would otherwise corrupt the very state that exists
    to survive interruptions.
    """

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    path = checkpoint_path(checkpoint.run_id)

    temporary = path.with_suffix(".json.tmp")

    temporary.write_text(
        json.dumps(checkpoint.model_dump(mode="json"), indent=2)
    )

    temporary.replace(path)


def clear_checkpoint(checkpoint: RunCheckpoint) -> None:
    """
    Delete the checkpoint once the run has finished successfully.

    Left in place, a completed run's checkpoint would cause the next
    identical request to return the old findings instead of researching
    afresh -- turning a resume mechanism into an accidental cache.
    """

    path = checkpoint_path(checkpoint.run_id)

    if path.exists():
        path.unlink()


def clear_workflow_checkpoints(directory: str | Path) -> int:
    """
    Delete the framework's workflow checkpoint files.

    These are written on every save and never read back, so without
    this they accumulate without limit -- around twenty files from a
    handful of runs.

    The framework names them by UUID, so there is no way to tell which
    files belong to which run. Clearing the whole directory therefore
    assumes no other analysis is in flight, which holds for the
    single-process CLI but would not hold if runs were ever executed
    concurrently.

    Returns the number of files removed.
    """

    path = Path(directory)

    if not path.exists():
        return 0

    removed = 0

    for file in path.glob("*.json"):

        try:
            file.unlink()
            removed += 1

        except OSError:
            # A file we cannot delete is not worth failing a completed
            # run over; it will be cleared on a later pass.
            pass

    return removed
