import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from opentelemetry import trace

from agent_framework.observability import configure_otel_providers
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor


# Span attributes carrying token usage. The exact key depends on the
# semantic-convention version in play, so several are accepted.
INPUT_TOKEN_KEYS = (
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.prompt_tokens",
)

OUTPUT_TOKEN_KEYS = (
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.completion_tokens",
)

.
NOISE_PREFIXES = (
    "edge_group.process",
    "message.send",
    "executor.process",
    "workflow.build",
)


def _first_attribute(span: ReadableSpan, keys) -> int:
    """Read the first present attribute from a list of candidates."""

    attributes = span.attributes or {}

    for key in keys:

        value = attributes.get(key)

        if isinstance(value, (int, float)):
            return int(value)

    return 0


class RunTimeline(SpanProcessor):
    """
    Prints one line per completed span, and tallies cost and latency.

    Registered as a span processor rather than an exporter so it sees
    spans as they finish, which is what makes it usable as live
    progress rather than a post-mortem.
    """

    def __init__(self, live: bool = True, log_path: str | None = None):

        self.live = live

        self.started = time.monotonic()

        # name -> [count, total_seconds, input_tokens, output_tokens]
        self.totals: dict[str, list[float]] = defaultdict(
            lambda: [0, 0.0, 0, 0]
        )

        # The terminal shows a filtered view for readability; the log
        # keeps everything, including the plumbing spans, so a finished
        # run can be examined properly afterwards.
        self.log = None

        if log_path:

            path = Path(log_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            # Truncated per run: this is "what happened last time", not
            # an archive. Keeping every run would grow without limit and
            # bury the one you care about.
            self.log = path.open("w", encoding="utf-8")

            self.log.write(f"run started {datetime.now().isoformat()}\n\n")

    def _write(self, line: str) -> None:
        """Append a line to the log file, if one is open."""

        if self.log is not None:
            self.log.write(line + "\n")
            self.log.flush()

    def on_start(self, span, parent_context=None):
        """Required by the interface; nothing to do on start."""

    def on_end(self, span: ReadableSpan) -> None:

        if span.start_time is None or span.end_time is None:
            return

        duration = (span.end_time - span.start_time) / 1e9

        prompt_tokens = _first_attribute(span, INPUT_TOKEN_KEYS)
        completion_tokens = _first_attribute(span, OUTPUT_TOKEN_KEYS)

        entry = self.totals[span.name]
        entry[0] += 1
        entry[1] += duration
        entry[2] += prompt_tokens
        entry[3] += completion_tokens

        elapsed = time.monotonic() - self.started

        tokens = ""

        if prompt_tokens or completion_tokens:
            tokens = f"  {prompt_tokens} in / {completion_tokens} out"

        line = (
            f"    [trace +{elapsed:6.1f}s] {span.name:<44} "
            f"{duration:6.2f}s{tokens}"
        )

        # The log keeps every span; the terminal keeps only the ones a
        # human watching a run can act on.
        self._write(line)

        if not self.live:
            return

        if span.name.startswith(NOISE_PREFIXES):
            return

        print(line)

    def shutdown(self) -> None:
        """Required by the interface."""

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        """Required by the interface."""

        return True

    # --------------------------------------------------------
    # Reporting
    # --------------------------------------------------------

    def report(self) -> str:
        """
        Summarise the run: where the time went, and where the tokens went.

        This is the artifact the brief asks for -- being able to read a
        trace and diagnose cost and latency from it.
        """

        if not self.totals:
            return "No spans were recorded."

        rows = sorted(
            self.totals.items(),
            key=lambda item: item[1][1],
            reverse=True,
        )

        lines = [
            "=" * 78,
            "RUN TRACE SUMMARY",
            "=" * 78,
            f"{'span':<44}{'calls':>6}{'total s':>10}{'tok in':>9}{'tok out':>9}",
            "-" * 78,
        ]

        total_calls = 0
        total_seconds = 0.0
        total_in = 0
        total_out = 0

        for name, (calls, seconds, tokens_in, tokens_out) in rows:

            lines.append(
                f"{name[:44]:<44}{int(calls):>6}{seconds:>10.2f}"
                f"{tokens_in:>9}{tokens_out:>9}"
            )

            total_calls += int(calls)
            total_seconds += seconds
            total_in += tokens_in
            total_out += tokens_out

        lines += [
            "-" * 78,
            f"{'TOTAL':<44}{total_calls:>6}{total_seconds:>10.2f}"
            f"{total_in:>9}{total_out:>9}",
            "=" * 78,
            f"wall clock: {time.monotonic() - self.started:.1f}s",
            "",
            "Span time overlaps (nested spans double-count), so the total "
            "above exceeds wall clock. Compare spans against each other "
            "rather than against the clock.",
        ]

        return "\n".join(lines)


# One timeline per process. Held at module level so the entry point can
# print its report after the run without threading it through every
# function in between.
TIMELINE: RunTimeline | None = None


DEFAULT_TRACE_LOG = "data/traces/last_run.log"


def setup_observability(
    live: bool = True,
    console_exporter: bool = False,
    log_path: str | None = DEFAULT_TRACE_LOG,
) -> RunTimeline:
    """
    Turn on tracing for this process.

    Call once at startup, before any agent runs.

    Args:
        live: print a filtered timeline to the terminal as spans finish.
        console_exporter: also dump full span payloads. Very verbose;
            useful for inspecting attributes, not for watching a run.
        log_path: file to write the complete trace to, overwritten each
            run. Pass None to disable.
    """

    global TIMELINE

    if TIMELINE is not None:
        return TIMELINE

    TIMELINE = RunTimeline(live=live, log_path=log_path)

    # This runs before the agent modules are imported, so their own
    # load_dotenv() calls have not happened yet. Without this, any
    # OTEL_* variable set in .env would be invisible and spans would
    # silently go nowhere.
    load_dotenv()

    # Reads the standard OTEL_* environment variables, so pointing at a
    # dashboard is configuration rather than a code change.
    configure_otel_providers(
        enable_console_exporters=console_exporter,
    )

    # Attach the timeline to whichever tracer provider was just set up.
    provider = trace.get_tracer_provider()

    if hasattr(provider, "add_span_processor"):
        provider.add_span_processor(TIMELINE)
    else:
        print(
            ">>> WARNING: tracer provider does not accept span "
            "processors; live timeline disabled"
        )

    return TIMELINE


@contextmanager
def trace_run(name: str, **attributes):
    """
    Wrap a whole analysis in a single root span.

    Without this every top-level operation starts its own trace, and a
    dashboard shows a run as a handful of disconnected fragments
    (workflow.build here, edge_group.process there) rather than one
    waterfall. Nesting everything under one span is what makes a run
    readable end to end.
    """

    tracer = trace.get_tracer("dailydollar.orchestration")

    with tracer.start_as_current_span(name) as span:

        for key, value in attributes.items():

            if value is not None:
                span.set_attribute(key, value)

        yield span


def print_report() -> None:
    """Print the end-of-run trace summary, and write it to the log."""

    if TIMELINE is None:
        return

    report = TIMELINE.report()

    print("\n" + report)

    TIMELINE._write("\n" + report)

    if TIMELINE.log is not None:

        print(f"\nfull trace written to {TIMELINE.log.name}")

        TIMELINE.log.close()
        TIMELINE.log = None
