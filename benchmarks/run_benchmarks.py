import os
import shlex
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

LOOMC = os.environ.get("LOOMC", "loom")

LANGUAGES = {
    "loom": {
        "build": ["{loomc}", "{src}", "-o", "{out}"],
        "run":   ["{out}.exe"],
        "ext":   ".loom",
    },
    "c": {
        "build": ["gcc", "-O2", "-o", "{out}.exe", "{src}"],
        "run":   ["{out}.exe"],
        "ext":   ".c",
    },
    "cpp": {
        "build": ["g++", "-O2", "-o", "{out}.exe", "{src}"],
        "run":   ["{out}.exe"],
        "ext":   ".cpp",
    },
    "python": {
        "build": None,
        "run":   ["python", "{src}"],
        "ext":   ".py",
    },
    "nodejs": {
        "build": None,
        "run":   ["node", "{src}"],
        "ext":   ".js",
    },
}


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def find_available_languages(bench_name: str) -> dict:
    available = {}
    bench_dir = os.path.join(ROOT, bench_name)
    for lang, cfg in LANGUAGES.items():
        src = os.path.join(bench_dir, f"{bench_name}{cfg['ext']}")
        if not os.path.exists(src):
            continue
        if cfg["build"] is not None:
            first = cfg["build"][0]
            if "{loomc}" in first:
                first = LOOMC.split()[0]
            if not _which(first):
                continue
        available[lang] = cfg
    return available


def build(lang: str, cfg: dict, bench_name: str, out_name: str) -> bool:
    bench_dir = os.path.join(ROOT, bench_name)
    src = os.path.join(bench_dir, f"{bench_name}{cfg['ext']}")
    out = os.path.join(bench_dir, out_name)

    if cfg["build"] is None:
        return True

    cmd = []
    for part in cfg["build"]:
        if "{loomc}" in part:
            formatted = part.replace("{loomc}", LOOMC)
            cmd.extend(formatted.split())
        else:
            cmd.append(part.format(src=src, out=out))

    print(f"  [build] {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=bench_dir)
    except FileNotFoundError as e:
        print(f"  [build] d: {e}")
        return False

    if r.returncode != 0:
        err = (r.stderr or r.stdout).strip()
        print(f"  [build] FAIL: {err[:300]}")
        return False
    return True


def run_once(lang: str, cfg: dict, bench_name: str, out_name: str):
    bench_dir = os.path.join(ROOT, bench_name)
    src = os.path.join(bench_dir, f"{bench_name}{cfg['ext']}")
    out = os.path.join(bench_dir, out_name)

    cmd = []
    for part in cfg["run"]:
        cmd.append(part.format(src=src, out=out))

    try:
        t0 = time.perf_counter()
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=600, cwd=bench_dir)
        t1 = time.perf_counter()
    except subprocess.TimeoutExpired:
        return None, "", False
    except FileNotFoundError:
        return None, "", False

    if r.returncode != 0:
        return None, r.stderr.strip(), False

    return t1 - t0, r.stdout.strip(), True


def bench_language(lang: str, cfg: dict, bench_name: str,
                   runs: int = 3) -> tuple[float | None, str]:
    out_name = f"_out_{lang}"
    if not build(lang, cfg, bench_name, out_name):
        return None, ""

    times = []
    output = ""
    for _ in range(runs):
        dt, out, ok = run_once(lang, cfg, bench_name, out_name)
        if not ok:
            return None, out
        times.append(dt)
        output = out

    return min(times), output


def cleanup(bench_name: str) -> None:
    bench_dir = os.path.join(ROOT, bench_name)
    for f in os.listdir(bench_dir):
        if f.startswith("_out_"):
            path = os.path.join(bench_dir, f)
            try:
                os.remove(path)
            except OSError:
                pass


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python run_benchmarks.py <bench_name>")
        print("       python run_benchmarks.py all")
        return 1

    target = sys.argv[1]
    if target == "all":
        names = sorted(
            d for d in os.listdir(ROOT)
            if os.path.isdir(os.path.join(ROOT, d))
            and not d.startswith("_")
            and d != "__pycache__"
        )
    else:
        names = [target]

    results = {}

    for bench_name in names:
        bench_dir = os.path.join(ROOT, bench_name)
        if not os.path.isdir(bench_dir):
            print(f"Unknown benchmark: {bench_name}")
            continue

        print(f"\n=== Benchmark: {bench_name} ===")
        langs = find_available_languages(bench_name)
        if not langs:
            print(" q ")
            continue

        results[bench_name] = {}

        for lang, cfg in langs.items():
            print(f"\n  [{lang}]")
            dt, out = bench_language(lang, cfg, bench_name)
            if dt is None:
                print(f"    FAILED: {out}")
                continue
            print(f"    time: {dt:.4f}s   output: {out!r}")
            results[bench_name][lang] = (dt, out)

        cleanup(bench_name)

    print("\n")
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)

    for bench_name, lang_results in results.items():
        if not lang_results:
            continue
        print(f"\n{bench_name}:")
        baseline_lang = "c" if "c" in lang_results else None
        baseline_time = lang_results[baseline_lang][0] if baseline_lang else None

        for lang, (dt, out) in sorted(lang_results.items(),
                                      key=lambda x: x[1][0]):
            if baseline_time and lang != baseline_lang:
                ratio = dt / baseline_time
                print(f"  {lang:10s} {dt:8.4f}s   ({ratio:6.2f}x vs C)   out={out!r}")
            else:
                marker = "  ← baseline" if lang == baseline_lang else ""
                print(f"  {lang:10s} {dt:8.4f}s   {'':>15s}   out={out!r}{marker}")

    return 0


if __name__ == "__main__":
    sys.exit(main())