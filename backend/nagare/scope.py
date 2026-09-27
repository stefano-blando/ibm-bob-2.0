"""Task-scoped write contracts: prompt + repository structure -> permitted / guarded / protected files.

Pipeline (each stage measured in experiments/scope_eval.py against real commit histories):
  1. Seeds: files the task is about. Explicit path/stem mentions, plus lexical retrieval (BM25)
     over file paths and top-level identifiers.
  2. Expansion: the seeds' neighbourhood in the import graph (Python AST with proper module
     resolution, JS/TS import statements) and, optionally, files that historically change together
     with the seeds (co-change mined from git history).
  3. Protection: owner-declared protected paths (nagare.json, never unlockable by the prompt),
     built-in guarded patterns (schemas, migrations, secrets, lockfiles, config — unlocked only
     when the prompt explicitly names the file), and files the prompt excludes ("do not touch X").
"""

import ast
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import networkx as nx

from nagare.models import ScopeContract, Policy
from nagare.paths import should_ignore

# Built-in guarded patterns: protected unless the task explicitly names the file.
KNOWN_SENSITIVE_PATTERNS = [
    r".*(database|db)/schema\.(sql|prisma)$",
    r"(.*/)?schema\.(sql|prisma)$",
    r".*(^|/)migrations/.*",
    r".*alembic\.ini$",
    r".*core/(config|secrets)\.py$",
    r".*settings/(production|secrets)\.py$",
    r"(.*/)?\.env(\..*)?$",
    r".*package-lock\.json$",
    r".*poetry\.lock$",
    r".*pnpm-lock\.yaml$",
    r".*cargo\.lock$",
    r".*yarn\.lock$",
    r".*uv\.lock$",
]

# Clauses that express a prohibition: they name files to protect, never files to seed.
NEGATION_RE = re.compile(r"\b(do\s+not|don't|dont|never|without|avoid|except|must\s+not|no\s+changes?\s+to)\b", re.IGNORECASE)

COMMON_STOPWORDS = {
    "app", "src", "lib", "test", "tests", "file", "files", "code", "repo", "add", "adds", "added",
    "the", "for", "with", "and", "into", "from", "refactor", "implement", "update", "updated",
    "fix", "fixes", "fixed", "create", "delete", "make", "change", "changes", "module", "use", "uses",
    "when", "that", "this", "not", "are", "was", "can", "should", "new", "all", "also", "only",
    "support", "allow", "allows", "remove", "removed", "move", "moved", "set", "get", "init", "main",
    "index", "none", "true", "false", "self", "return", "value", "values", "some", "more", "than",
    "via", "per", "its", "has", "have", "been", "which", "into", "out", "now", "instead", "see",
}

JS_TS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
PY_DEF_RE = re.compile(r"^(?:async\s+)?(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
JS_DEF_RE = re.compile(r"(?:function|class|const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)")
MAX_COCHANGE_COMMIT_FILES = 20


def _split_identifier(text: str) -> List[str]:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return [t.lower() for t in re.split(r"[^A-Za-z0-9]+", text) if t]


def _stem(token: str) -> str:
    for suffix in ("ations", "ation", "ings", "ing", "ers", "er", "ies", "es", "ed", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return token


def _tokens(text: str) -> List[str]:
    return [_stem(t) for t in _split_identifier(text) if len(t) >= 3 and t not in COMMON_STOPWORDS]


class ScopeSynthesizer:
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).resolve()
        self.graph = nx.DiGraph()
        self._doc_tokens: Dict[Path, List[str]] = {}
        self._module_index: Dict[str, Path] = {}
        self._module_of: Dict[Path, str] = {}
        self._history_cutoff = "HEAD"
        self._cochange: Optional[Tuple[Counter, Dict[Path, Counter]]] = None

    def _should_ignore(self, path: Path) -> bool:
        return should_ignore(path)

    # ------------------------------------------------------------------ prompt parsing

    @staticmethod
    def split_intent(task_prompt: str):
        """Split a prompt into (positive_text, negated_text) at clause level."""
        positive, negated = [], []
        for clause in re.split(r"\.(?=\s|$)|[;\n]|,\s*(?:but|and)\s+|\bbut\b", task_prompt):
            # "Implement X in a.py without touching b.py": a.py is positive, b.py is negated.
            m = NEGATION_RE.search(clause)
            if m:
                positive.append(clause[:m.start()])
                negated.append(clause[m.start():])
            else:
                positive.append(clause)
        return " ".join(positive), " ".join(negated)

    @staticmethod
    def _mentions(text: str, node: Path) -> bool:
        if node.as_posix() in text:
            return True
        return re.search(rf"(?<![A-Za-z0-9_]){re.escape(node.stem)}(?![A-Za-z0-9_])", text) is not None

    # ------------------------------------------------------------------ import graph

    def _python_roots(self, py_files: List[Path]) -> List[Path]:
        """sys.path-like roots: the repo root plus parents of top-level packages (e.g. src/)."""
        roots = {Path(".")}
        package_dirs = {f.parent for f in py_files if f.name == "__init__.py"}
        for pkg in package_dirs:
            if pkg.parent not in package_dirs:
                roots.add(pkg.parent)
        return sorted(roots, key=lambda p: len(p.parts), reverse=True)

    def _build_module_index(self, py_files: List[Path]) -> None:
        self._module_index = {}
        for root in reversed(self._python_roots(py_files)):  # deeper roots win
            for rel in py_files:
                try:
                    sub = rel.relative_to(root) if root != Path(".") else rel
                except ValueError:
                    continue
                parts = list(sub.with_suffix("").parts)
                if parts and parts[-1] == "__init__":
                    parts = parts[:-1]
                if parts:
                    self._module_index[".".join(parts)] = rel
        # The deepest root gives a file its canonical module name (src/flask/app.py -> flask.app).
        self._module_of = {}
        for dotted, rel in self._module_index.items():
            if rel not in self._module_of or len(dotted) < len(self._module_of[rel]):
                self._module_of[rel] = dotted

    def _resolve_module(self, dotted: str) -> Optional[Path]:
        return self._module_index.get(dotted)

    def _package_of(self, rel: Path) -> str:
        dotted = self._module_of.get(rel, "")
        return dotted if rel.name == "__init__.py" else dotted.rpartition(".")[0]

    def _python_edges(self, rel: Path, tree: ast.AST) -> Iterable[Path]:
        package = None
        for node in ast.walk(tree):
            targets: List[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    if package is None:
                        package = self._package_of(rel)
                    pkg_parts = package.split(".") if package else []
                    keep = len(pkg_parts) - (node.level - 1)
                    prefix = ".".join(pkg_parts[:max(keep, 0)])
                    base = ".".join(x for x in (prefix, base) if x)
                for alias in node.names:
                    targets.append(f"{base}.{alias.name}" if base else alias.name)
                if base:
                    targets.append(base)
            elif isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
                if name in ("import_module", "__import__") and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        targets.append(arg.value)
            for dotted in targets:
                # "import a.b.c" / "from a.b import c": longest existing module prefix wins.
                parts = dotted.split(".")
                for cut in range(len(parts), 0, -1):
                    hit = self._resolve_module(".".join(parts[:cut]))
                    if hit is not None:
                        if hit != rel:
                            yield hit
                        break

    def _parse_js_ts_imports(self, rel_path: Path, content: str):
        patterns = [
            r"""(?:import|export)\s+(?:.*?from\s+)?['"]([^'"]+)['"]""",
            r"""require\(['"]([^'"]+)['"]\)""",
            r"""import\(['"]([^'"]+)['"]\)""",
        ]
        source_dir = (self.repo_root / rel_path).parent
        for pat in patterns:
            for match in re.findall(pat, content):
                if match.startswith("."):
                    candidate = (source_dir / match).resolve()
                    resolved = None
                    if candidate.is_file():
                        resolved = candidate
                    else:
                        for ext in [".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", "/index.js", "/index.jsx"]:
                            ext_candidate = Path(str(candidate) + ext)
                            if ext_candidate.is_file():
                                resolved = ext_candidate
                                break
                    if resolved and (self.repo_root == resolved or self.repo_root in resolved.parents):
                        try:
                            self.graph.add_edge(rel_path, resolved.relative_to(self.repo_root))
                        except ValueError:
                            pass

    def build_dependency_graph(self) -> nx.DiGraph:
        self.graph.clear()
        self._doc_tokens = {}
        source_files = [
            f.relative_to(self.repo_root) for f in self.repo_root.rglob("*")
            if f.is_file() and (f.suffix == ".py" or f.suffix in JS_TS_EXTENSIONS)
            and not self._should_ignore(f.relative_to(self.repo_root))
        ]
        py_files = [f for f in source_files if f.suffix == ".py"]
        self._build_module_index(py_files)

        for rel_path in source_files:
            self.graph.add_node(rel_path)
            try:
                content = (self.repo_root / rel_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            idents = PY_DEF_RE.findall(content) if rel_path.suffix == ".py" else JS_DEF_RE.findall(content)
            self._doc_tokens[rel_path] = _tokens(" ".join(rel_path.with_suffix("").parts)) * 3 + _tokens(" ".join(idents))
            if rel_path.suffix == ".py":
                try:
                    tree = ast.parse(content)
                except (SyntaxError, ValueError):
                    continue
                for target in self._python_edges(rel_path, tree):
                    self.graph.add_edge(rel_path, target)
            else:
                self._parse_js_ts_imports(rel_path, content)

        return self.graph

    # ------------------------------------------------------------------ seeds

    def _mention_seeds(self, positive_text: str) -> List[Path]:
        seeds = [
            node for node in self.graph.nodes
            if node.as_posix() in positive_text
            or (node.stem not in COMMON_STOPWORDS and node.stem != "__init__" and self._mentions(positive_text, node))
        ]
        if seeds:
            return seeds
        # Legacy fallback: prompt keywords as substrings of paths.
        keywords = [kw for kw in re.findall(r"\b[a-zA-Z]{3,}\b", positive_text.lower()) if kw not in COMMON_STOPWORDS]
        return [node for node in self.graph.nodes if any(kw in node.as_posix().lower() for kw in keywords)]

    def _bm25_seeds(self, positive_text: str, top_k: int = 5, rel_threshold: float = 0.35) -> List[Path]:
        explicit = [n for n in self.graph.nodes if n.as_posix() in positive_text]
        query = set(_tokens(positive_text))
        if not query or not self._doc_tokens:
            return explicit
        n_docs = len(self._doc_tokens)
        avg_len = sum(len(t) for t in self._doc_tokens.values()) / n_docs or 1.0
        df = Counter()
        for toks in self._doc_tokens.values():
            df.update(set(toks))
        scores = {}
        for doc, toks in self._doc_tokens.items():
            tf = Counter(toks)
            score = 0.0
            for q in query:
                if q in tf:
                    idf = math.log(1 + (n_docs - df[q] + 0.5) / (df[q] + 0.5))
                    score += idf * tf[q] * 2.2 / (tf[q] + 1.2 * (0.25 + 0.75 * len(toks) / avg_len))
            if score > 0:
                scores[doc] = score
        if not scores:
            return explicit
        best = max(scores.values())
        ranked = sorted(scores, key=scores.get, reverse=True)
        return list(dict.fromkeys(explicit + [d for d in ranked[:top_k] if scores[d] >= rel_threshold * best]))

    # ------------------------------------------------------------------ co-change

    def set_history_cutoff(self, rev: str) -> None:
        """Mine co-change only from history up to `rev` (evaluation: no peeking at the future)."""
        self._history_cutoff = rev
        self._cochange = None

    def _cochange_stats(self) -> Tuple[Counter, Dict[Path, Counter]]:
        if self._cochange is not None:
            return self._cochange
        single: Counter = Counter()
        pairs: Dict[Path, Counter] = defaultdict(Counter)
        try:
            out = subprocess.run(
                ["git", "log", "--no-merges", "--format=%x1e", "--name-only", "-n", "3000", self._history_cutoff, "--", "."],
                cwd=self.repo_root, capture_output=True, text=True, check=True,
            ).stdout
        except (subprocess.CalledProcessError, OSError):
            self._cochange = (single, pairs)
            return self._cochange
        # git prints paths relative to the repository top level; make them relative to repo_root.
        try:
            top = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=self.repo_root,
                                      capture_output=True, text=True, check=True).stdout.strip()).resolve()
            prefix = self.repo_root.relative_to(top)
        except (subprocess.CalledProcessError, OSError, ValueError):
            prefix = Path(".")
        for block in out.split("\x1e"):
            files = []
            for line in block.strip().splitlines():
                p = Path(line)
                if prefix != Path("."):
                    try:
                        p = p.relative_to(prefix)
                    except ValueError:
                        continue
                if not should_ignore(p):
                    files.append(p)
            if not files or len(files) > MAX_COCHANGE_COMMIT_FILES:
                continue
            single.update(files)
            for a in files:
                for b in files:
                    if a != b:
                        pairs[a][b] += 1
        self._cochange = (single, pairs)
        return self._cochange

    def _cochange_neighbours(self, seeds: Iterable[Path], min_support: int = 2, min_conf: float = 0.3, per_seed: int = 5) -> Set[Path]:
        single, pairs = self._cochange_stats()
        found: Set[Path] = set()
        for seed in seeds:
            if single[seed] == 0:
                continue
            ranked = sorted(pairs[seed].items(), key=lambda kv: kv[1], reverse=True)
            picked = [f for f, n in ranked if n >= min_support and n / single[seed] >= min_conf]
            found.update(f for f in picked[:per_seed] if (self.repo_root / f).exists())
        return found

    # ------------------------------------------------------------------ expansion

    def _expand(self, seeds: Iterable[Path], expand: str) -> Set[Path]:
        permitted: Set[Path] = set(seeds)
        if expand == "none":
            return permitted
        frontier = set(seeds)
        hops = 2 if expand == "both2" else 1
        for _ in range(hops):
            nxt: Set[Path] = set()
            for node in frontier:
                if node not in self.graph:
                    continue
                nxt.update(self.graph.successors(node))
                if expand in ("both1", "both2"):
                    nxt.update(self.graph.predecessors(node))
            nxt -= permitted
            permitted |= nxt
            frontier = nxt
        return permitted

    # ------------------------------------------------------------------ contract

    def _load_config(self) -> Tuple[List[str], List[str], Set[Path]]:
        protected_patterns: List[str] = []
        guarded_patterns = list(KNOWN_SENSITIVE_PATTERNS)
        extra_permitted: Set[Path] = set()
        for cfg_name in ("nagare.json", ".nagarerc.json", ".nagare.json"):
            cfg_path = self.repo_root / cfg_name
            if not cfg_path.is_file():
                continue
            try:
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            # "protected": owner policy, the prompt can never unlock it.
            protected_patterns.extend(p for p in cfg.get("protected", []) if isinstance(p, str))
            # "extra_restricted" (legacy name) behaves like owner policy too.
            protected_patterns.extend(p for p in cfg.get("extra_restricted", []) if isinstance(p, str))
            extra_permitted.update(Path(p) for p in cfg.get("extra_permitted", []) if isinstance(p, str))
        return protected_patterns, guarded_patterns, extra_permitted

    def synthesize_scope(
        self,
        task_prompt: str,
        policy: Policy = Policy.LANE,
        rebuild: bool = True,
        seed: str = "bm25",
        expand: str = "both1",
        cochange: bool = True,
    ) -> ScopeContract:
        if rebuild or self.graph.number_of_nodes() == 0:
            self.build_dependency_graph()
        positive_text, negated_text = self.split_intent(task_prompt)
        protected_patterns, guarded_patterns, extra_permitted = self._load_config()

        restricted: Set[Path] = set()
        unlocked: Set[Path] = set()
        tracked = self._tracked_files()
        for rel in tracked:
            rel_str = rel.as_posix()
            if any(re.match(p, rel_str) for p in protected_patterns):
                restricted.add(rel)
            elif any(re.match(p, rel_str) for p in guarded_patterns):
                if rel_str in positive_text or (rel.stem not in COMMON_STOPWORDS and self._mentions(positive_text, rel)):
                    # The task explicitly names this guarded file: the human asked for it.
                    unlocked.add(rel)
                else:
                    restricted.add(rel)
            elif negated_text and (rel_str in negated_text or (
                rel.stem not in COMMON_STOPWORDS and self._mentions(negated_text, rel)
            )):
                # "Do not touch X": X becomes protected for this task.
                restricted.add(rel)

        seeds = self._bm25_seeds(positive_text) if seed == "bm25" else self._mention_seeds(positive_text)
        seeds = [s for s in seeds if s not in restricted]
        permitted = self._expand(seeds, expand)
        if cochange and seeds:
            permitted |= self._cochange_neighbours(seeds)
        permitted = {p for p in permitted if p not in restricted}

        # No signal at all: fall back to every non-restricted source file.
        if not permitted:
            permitted = {n for n in self.graph.nodes if n not in restricted}
        permitted |= {p for p in extra_permitted if p not in restricted}
        # Explicitly named guarded files are part of the task.
        permitted |= unlocked

        return ScopeContract(
            permitted_paths=permitted,
            restricted_paths=restricted,
            task_intent=task_prompt,
            sensitive_patterns=protected_patterns + guarded_patterns,
            policy=policy,
            unlocked_paths=unlocked,
        )

    def _tracked_files(self) -> List[Path]:
        try:
            out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                                 cwd=self.repo_root, capture_output=True, check=True).stdout
            files = [Path(p) for p in out.decode("utf-8", "surrogateescape").split("\0") if p]
        except (subprocess.CalledProcessError, OSError):
            files = [p.relative_to(self.repo_root) for p in self.repo_root.rglob("*") if p.is_file()]
        return [f for f in files if not should_ignore(f) and (self.repo_root / f).is_file()]
