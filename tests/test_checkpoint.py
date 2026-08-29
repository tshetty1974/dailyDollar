"""
Test 9 — run-level checkpointing. No LLM, no network, no cost.

Checks the logic that decides what to skip on a resume. The real
end-to-end proof is interrupting a live run (see the instructions
printed at the end), but every rule that decision depends on is
verifiable for free.

Run:  PYTHONPATH=src python3 tests/test_checkpoint.py
"""

from models import Horizon, InvestmentRequest, RiskAppetite
from memory.checkpoint import (
    checkpoint_path,
    clear_checkpoint,
    load_checkpoint,
    run_id_for,
    save_checkpoint,
)


DEBATE_KEY = "Bull vs Skeptic Debate"


def check(label, condition):
    print(f"{'PASS' if condition else 'FAIL'}  {label}")


request = InvestmentRequest(
    user_id="checkpoint_test_user",
    tickers=["NVDA", "AMD"],
    amount=50_000,
    risk_appetite=RiskAppetite.MODERATE,
    horizon=Horizon.LONG,
    constraints=["No more than 40% in a single position"],
)


# ------------------------------------------------------------
# 1. The run id must be stable, and must change when it should
# ------------------------------------------------------------

check("same request gives the same run id", run_id_for(request) == run_id_for(request))

check(
    "ticker order does not change the run id",
    run_id_for(request)
    == run_id_for(request.model_copy(update={"tickers": ["AMD", "NVDA"]})),
)

check(
    "a different amount is a different run",
    run_id_for(request) != run_id_for(request.model_copy(update={"amount": 10_000})),
)

check(
    "a different risk appetite is a different run",
    run_id_for(request)
    != run_id_for(
        request.model_copy(update={"risk_appetite": RiskAppetite.AGGRESSIVE})
    ),
)


# ------------------------------------------------------------
# 2. Fresh start
# ------------------------------------------------------------

path = checkpoint_path(run_id_for(request))
if path.exists():
    path.unlink()

fresh = load_checkpoint(request)

check("a new run starts empty", fresh.findings == {})
check("nothing is researched yet", not fresh.has_research("NVDA"))


# ------------------------------------------------------------
# 3. Research NVDA, crash before AMD
# ------------------------------------------------------------

fresh.findings["NVDA"] = {
    "Fundamentals Analyst": ["NVDA fundamentals text"],
    "Technical Analyst": ["NVDA technical text"],
}

save_checkpoint(fresh)

# A brand new object, as a restarted process would see.
resumed = load_checkpoint(request)

check("NVDA's research survived the crash", resumed.has_research("NVDA"))
check("AMD is correctly still outstanding", not resumed.has_research("AMD"))
check(
    "the findings themselves survived",
    resumed.findings["NVDA"]["Technical Analyst"] == ["NVDA technical text"],
)
check("NVDA has not been debated yet", not resumed.has_debate("NVDA", DEBATE_KEY))

print(f"\n  progress reads: {resumed.progress(DEBATE_KEY)}")


# ------------------------------------------------------------
# 4. Debate NVDA, crash again
# ------------------------------------------------------------

resumed.findings["NVDA"][DEBATE_KEY] = ["bull", "skeptic", "bull reply"]
save_checkpoint(resumed)

again = load_checkpoint(request)

check("NVDA's debate survived", again.has_debate("NVDA", DEBATE_KEY))
check(
    "AMD still needs both research and debate",
    not again.has_research("AMD") and not again.has_debate("AMD", DEBATE_KEY),
)

print(f"\n  progress reads: {again.progress(DEBATE_KEY)}")


# ------------------------------------------------------------
# 5. Finishing clears the checkpoint
# ------------------------------------------------------------
#
# Otherwise the next identical request would replay these findings
# instead of researching afresh -- a resume turning into a stale cache.

clear_checkpoint(again)

check("checkpoint file removed on success", not path.exists())
check("a later identical request starts clean", load_checkpoint(request).findings == {})


print(
    """
======================================================================
END-TO-END RESUME DEMO (do this once for the write-up)
======================================================================
1. Run:    PYTHONPATH=src python3 tests/test_orchestration.py
2. Wait for  '[NVDA] ORCHESTRATION COMPLETE'  and the AMD run to begin
3. Press Ctrl-C
4. Run the same command again

Expected second run:
   >>> RESUMING RUN <id>
   >>> already done: NVDA (researched)
   >>> [NVDA] already researched - skipping

That is requirement 3.7: a long multi-stock run resuming after an
interruption without restarting from scratch. Screenshot it.
======================================================================
"""
)
