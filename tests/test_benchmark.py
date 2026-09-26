import subprocess
from pathlib import Path
from nagare.benchmark import run_micro_rollback_benchmark, BenchmarkResult

def test_micro_rollback_benchmark_latency(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)

    dummy_file = tmp_path / "protected.py"
    dummy_file.write_text("ORIGINAL = 1\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)

    result = run_micro_rollback_benchmark(repo_root=tmp_path, iterations=10)
    assert isinstance(result, BenchmarkResult)
    assert result.iterations == 10
    assert result.avg_latency_ms > 0.0
    # Must be under 50ms per rollback on any standard machine
    assert result.avg_latency_ms < 50.0
    assert result.corruptions_blocked == 10
    assert dummy_file.read_text() == "ORIGINAL = 1\n"
