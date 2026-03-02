#!/usr/bin/env python3
"""Speakly benchmark — measure TTS provider timing and progressive vs full-file."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Text fixtures
# ---------------------------------------------------------------------------

TEXTS = {
    "short": (
        "The quick brown fox jumps over the lazy dog. "
        "Pack my box with five dozen liquor jugs. "
        "How vexingly quick daft zebras jump. "
        "The five boxing wizards jump quickly."
    ),
    "medium": (
        "Artificial intelligence has transformed the way we interact with technology. "
        "From voice assistants that understand natural language to recommendation systems "
        "that predict our preferences, AI is woven into the fabric of our daily lives. "
        "Machine learning algorithms process vast amounts of data to identify patterns "
        "and make decisions that would be impossible for humans to compute manually. "
        "Natural language processing enables computers to understand, interpret, and "
        "generate human language in meaningful ways. Computer vision systems can now "
        "identify objects, faces, and scenes with remarkable accuracy. "
        "The development of transformer architectures has revolutionized how we approach "
        "sequence-to-sequence tasks, leading to breakthroughs in translation, summarization, "
        "and text generation. As these technologies continue to evolve, they promise to "
        "reshape industries from healthcare to education, creating new opportunities "
        "while also raising important questions about ethics, privacy, and the future of work."
    ),
    "long": (
        "The history of human communication is a fascinating journey that spans thousands of years. "
        "From the earliest cave paintings discovered in Lascaux, France, dating back over seventeen "
        "thousand years, to the instant digital messages we send today, our species has always "
        "sought better ways to share ideas and information. The invention of writing around 3400 BC "
        "in ancient Mesopotamia was perhaps the single most transformative development in this "
        "history, allowing knowledge to be preserved and transmitted across generations. "
        "The Phoenician alphabet, developed around 1050 BC, simplified writing systems and made "
        "literacy more accessible. The Greeks adapted this alphabet, adding vowels, and their "
        "system became the foundation for Latin script used across much of the world today. "
        "The invention of the printing press by Johannes Gutenberg in 1440 democratized access "
        "to information, catalyzing the Renaissance, the Reformation, and the Scientific Revolution. "
        "Books became affordable, literacy rates soared, and ideas could spread faster than ever before. "
        "The telegraph, invented in the 1830s, was the first technology to send messages "
        "electronically over long distances, fundamentally changing commerce and news reporting. "
        "Alexander Graham Bell's telephone in 1876 added the human voice to long-distance "
        "communication, making conversations possible across vast distances. "
        "Radio broadcasting in the early twentieth century brought news and entertainment "
        "into homes worldwide, creating shared cultural experiences on an unprecedented scale. "
        "Television added visual imagery to broadcasting, transforming how people consumed "
        "information and entertainment. The internet, originally developed as a military "
        "communication network in the 1960s, evolved into the most powerful communication "
        "tool in human history. Email replaced much of traditional mail, websites made "
        "information instantly accessible, and social media platforms connected billions "
        "of people in ways previously unimaginable. Today, artificial intelligence is "
        "adding yet another layer to communication, with voice synthesis making it possible "
        "for machines to speak with increasingly natural and expressive voices, bridging "
        "the gap between written text and spoken word in ways that benefit accessibility, "
        "education, and creative expression around the globe."
    ),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    provider: str
    size: str
    mode: str  # "full-file" or "progressive"
    synth_time_s: float
    first_chunk_s: float | None = None  # progressive only


@dataclass
class E2EResult:
    provider: str
    first_audio_s: float | None
    total_s: float
    progressive: bool


@dataclass
class AggResult:
    provider: str
    size: str
    mode: str
    runs: int
    first_audio_mean: float | None = None
    first_audio_std: float | None = None
    synth_mean: float = 0.0
    synth_std: float = 0.0


# ---------------------------------------------------------------------------
# Headless benchmarks (direct Python calls, no Qt)
# ---------------------------------------------------------------------------


def _default_voice(provider_name: str) -> str:
    """Return sensible default voice for a provider."""
    defaults = {
        "edge": "en-US-AriaNeural",
        "openai": "nova",
        "elevenlabs": "Rachel",
        "inworld": "Alex",
    }
    return defaults.get(provider_name, "default")


def _run_full_file(provider_name: str, text: str, voice: str | None, speed: float) -> RunResult:
    """Benchmark a full-file synthesis call."""
    from speakly.providers import get_provider

    provider = get_provider(provider_name)
    voice = voice or _default_voice(provider_name)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        out_path = Path(f.name)

    try:
        t0 = time.perf_counter()
        provider.synthesize(text, voice, speed, out_path)
        synth_time = time.perf_counter() - t0
    finally:
        out_path.unlink(missing_ok=True)

    return RunResult(
        provider=provider_name,
        size="",
        mode="full-file",
        synth_time_s=synth_time,
    )


def _run_progressive(provider_name: str, text: str, voice: str | None, speed: float) -> RunResult:
    """Benchmark progressive synthesis via ProgressiveOrchestrator."""
    from speakly.progressive_core import ProgressiveCallbacks, ProgressiveOrchestrator
    from speakly.progressive_inworld import InworldProgressiveAdapter

    voice = voice or _default_voice(provider_name)
    first_chunk_time: list[float] = []
    t0 = time.perf_counter()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "output.mp3"
        adapter = InworldProgressiveAdapter()

        def on_chunk(p: Path) -> None:
            if not first_chunk_time:
                first_chunk_time.append(time.perf_counter() - t0)

        callbacks = ProgressiveCallbacks(
            on_chunk_ready=on_chunk,
            on_status=lambda s: None,
            on_done=lambda p: None,
            on_error=lambda e: None,
        )
        orchestrator = ProgressiveOrchestrator(
            adapter=adapter,
            text=text,
            voice=voice or "",
            speed=speed,
            output_path=out_path,
            callbacks=callbacks,
        )
        orchestrator.run()

    synth_time = time.perf_counter() - t0
    return RunResult(
        provider=provider_name,
        size="",
        mode="progressive",
        synth_time_s=synth_time,
        first_chunk_s=first_chunk_time[0] if first_chunk_time else None,
    )


def _aggregate(results: list[RunResult]) -> AggResult:
    """Aggregate multiple runs into mean ± std."""
    if not results:
        raise ValueError("No results to aggregate")

    synths = [r.synth_time_s for r in results]
    first_chunks = [r.first_chunk_s for r in results if r.first_chunk_s is not None]

    return AggResult(
        provider=results[0].provider,
        size=results[0].size,
        mode=results[0].mode,
        runs=len(results),
        synth_mean=_mean(synths),
        synth_std=_std(synths),
        first_audio_mean=_mean(first_chunks) if first_chunks else None,
        first_audio_std=_std(first_chunks) if first_chunks else None,
    )


# ---------------------------------------------------------------------------
# E2E UI benchmark (subprocess with --bench-exit)
# ---------------------------------------------------------------------------


def _run_e2e(provider_name: str, text: str, voice: str | None) -> E2EResult | None:
    """Run Speakly as a subprocess with --bench-exit and parse JSON summary."""
    cmd = ["uv", "run", "speakly", text, "--provider", provider_name, "--bench-exit"]
    if voice:
        cmd.extend(["--voice", voice])

    env = {**os.environ, "SPEAKLY_BENCH": "1"}
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
    except subprocess.TimeoutExpired:
        return None

    # Parse JSON summary from stderr
    for line in result.stderr.splitlines():
        line = line.strip()
        if line.startswith("{") and '"bench_summary"' in line:
            try:
                data = json.loads(line)
                return E2EResult(
                    provider=provider_name,
                    first_audio_s=data.get("first_audio_s"),
                    total_s=data.get("total_s", 0),
                    progressive=data.get("progressive", False),
                )
            except json.JSONDecodeError:
                continue
    return None


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _fmt_time(val: float | None, std: float | None = None) -> str:
    if val is None:
        return "-"
    if std is not None and std > 0:
        return f"{val:.2f} \u00b1{std:.2f}"
    return f"{val:.2f}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

app = typer.Typer(help="Speakly Benchmark — measure TTS timing across providers.")
console = Console()


@app.command()
def main(
    providers: str = typer.Option("edge", help="Comma-separated providers to benchmark"),
    sizes: str = typer.Option("short,medium", help="Comma-separated text sizes: short,medium,long"),
    iterations: int = typer.Option(3, "--iterations", "-n", help="Runs per configuration"),
    json_out: Path | None = typer.Option(None, "--json-out", help="Write raw results as JSON"),
    e2e: bool = typer.Option(False, "--e2e", help="Also run E2E UI benchmarks (slower)"),
    e2e_runs: int = typer.Option(2, "--e2e-runs", help="Number of E2E runs per config"),
):
    from tqdm import tqdm

    # Trigger provider registration
    import speakly.providers.edge  # noqa: F401

    try:
        import speakly.providers.inworld  # noqa: F401
    except (ImportError, Exception):
        pass
    try:
        import speakly.providers.openai  # noqa: F401
    except (ImportError, Exception):
        pass
    try:
        import speakly.providers.elevenlabs  # noqa: F401
    except (ImportError, Exception):
        pass

    provider_list = [p.strip() for p in providers.split(",")]
    size_list = [s.strip() for s in sizes.split(",")]

    all_results: list[RunResult] = []
    agg_results: list[AggResult] = []

    # Compute total headless runs for progress bar
    total_headless = 0
    for prov in provider_list:
        for size in size_list:
            total_headless += iterations  # full-file
            if prov == "inworld":
                total_headless += iterations  # progressive

    # --- Headless benchmarks ---
    console.print("\n[bold]Speakly Benchmark - Headless Provider Timing[/bold]")
    console.print("=" * 50)

    with tqdm(total=total_headless, desc="Benchmarking", unit="run") as pbar:
        for prov in provider_list:
            for size in size_list:
                text = TEXTS.get(size, TEXTS["short"])

                # Full-file runs
                runs: list[RunResult] = []
                for _ in range(iterations):
                    try:
                        r = _run_full_file(prov, text, None, 1.0)
                        r.size = size
                        runs.append(r)
                        all_results.append(r)
                    except Exception as exc:
                        console.print(f"  [red]Error ({prov}/{size}/full-file): {exc}[/red]")
                    pbar.update(1)

                if runs:
                    agg_results.append(_aggregate(runs))

                # Progressive runs (Inworld only)
                if prov == "inworld":
                    prog_runs: list[RunResult] = []
                    for _ in range(iterations):
                        try:
                            r = _run_progressive(prov, text, None, 1.0)
                            r.size = size
                            prog_runs.append(r)
                            all_results.append(r)
                        except Exception as exc:
                            console.print(f"  [red]Error ({prov}/{size}/progressive): {exc}[/red]")
                        pbar.update(1)

                    if prog_runs:
                        agg_results.append(_aggregate(prog_runs))

    # --- Print headless results table ---
    table = Table(title="Headless Provider Timing")
    table.add_column("Provider", style="cyan")
    table.add_column("Size", style="green")
    table.add_column("Mode")
    table.add_column("1stAudio(s)", justify="right")
    table.add_column("SynthTotal(s)", justify="right")
    table.add_column("Runs", justify="right")

    for agg in agg_results:
        table.add_row(
            agg.provider,
            agg.size,
            agg.mode,
            _fmt_time(agg.first_audio_mean, agg.first_audio_std),
            _fmt_time(agg.synth_mean, agg.synth_std),
            str(agg.runs),
        )

    console.print(table)

    # --- Progressive A/B delta ---
    _print_progressive_delta(agg_results)

    # --- E2E UI benchmarks ---
    e2e_results: list[E2EResult] = []
    if e2e:
        console.print("\n[bold]E2E UI Benchmark[/bold]")
        console.print("=" * 50)

        e2e_total = len(provider_list) * e2e_runs
        with tqdm(total=e2e_total, desc="E2E runs", unit="run") as pbar:
            for prov in provider_list:
                text = TEXTS["short"]
                for _ in range(e2e_runs):
                    result = _run_e2e(prov, text, None)
                    if result:
                        e2e_results.append(result)
                    pbar.update(1)

        if e2e_results:
            e2e_table = Table(title="E2E UI Overhead")
            e2e_table.add_column("Provider", style="cyan")
            e2e_table.add_column("FirstAudio(s)", justify="right")
            e2e_table.add_column("Total(s)", justify="right")
            e2e_table.add_column("Progressive")

            # Group by provider
            by_prov: dict[str, list[E2EResult]] = {}
            for r in e2e_results:
                by_prov.setdefault(r.provider, []).append(r)

            for prov, results in by_prov.items():
                fa_vals = [r.first_audio_s for r in results if r.first_audio_s is not None]
                total_vals = [r.total_s for r in results]
                prog = any(r.progressive for r in results)
                e2e_table.add_row(
                    prov,
                    _fmt_time(_mean(fa_vals) if fa_vals else None, _std(fa_vals) if len(fa_vals) >= 2 else None),
                    _fmt_time(_mean(total_vals), _std(total_vals) if len(total_vals) >= 2 else None),
                    "yes" if prog else "no",
                )

            console.print(e2e_table)

    # --- JSON output ---
    if json_out:
        output = {
            "headless": [
                {
                    "provider": agg.provider,
                    "size": agg.size,
                    "mode": agg.mode,
                    "runs": agg.runs,
                    "first_audio_mean_s": agg.first_audio_mean,
                    "first_audio_std_s": agg.first_audio_std,
                    "synth_mean_s": agg.synth_mean,
                    "synth_std_s": agg.synth_std,
                }
                for agg in agg_results
            ],
            "e2e": [
                {
                    "provider": r.provider,
                    "first_audio_s": r.first_audio_s,
                    "total_s": r.total_s,
                    "progressive": r.progressive,
                }
                for r in e2e_results
            ],
            "raw_runs": [
                {
                    "provider": r.provider,
                    "size": r.size,
                    "mode": r.mode,
                    "synth_time_s": r.synth_time_s,
                    "first_chunk_s": r.first_chunk_s,
                }
                for r in all_results
            ],
        }
        json_out.write_text(json.dumps(output, indent=2))
        console.print(f"\nResults written to {json_out}")


def _print_progressive_delta(agg_results: list[AggResult]) -> None:
    """Print progressive vs full-file delta for Inworld."""
    inworld_by_size: dict[str, dict[str, AggResult]] = {}
    for agg in agg_results:
        if agg.provider == "inworld":
            inworld_by_size.setdefault(agg.size, {})[agg.mode] = agg

    if not inworld_by_size:
        return

    console.print("\n[bold]Progressive A/B Delta (inworld):[/bold]")
    for size, modes in sorted(inworld_by_size.items()):
        prog = modes.get("progressive")
        full = modes.get("full-file")
        if not prog or not full or prog.first_audio_mean is None:
            continue

        delta = full.synth_mean - prog.first_audio_mean
        pct = (delta / full.synth_mean * 100) if full.synth_mean > 0 else 0
        console.print(
            f"  {size}: 1st audio {delta:.2f}s earlier "
            f"({prog.first_audio_mean:.2f}s vs {full.synth_mean:.2f}s) "
            f"- {pct:.0f}% faster"
        )


if __name__ == "__main__":
    app()
