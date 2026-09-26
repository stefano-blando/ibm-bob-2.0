import ast
import re
from pathlib import Path
from typing import Set, Dict, List
import networkx as nx
from nagare.models import ScopeContract

KNOWN_SENSITIVE_PATTERNS = [
    r".*(database|db)/schema\.(sql|prisma)$",
    r".*(database|db)/migrations/.*",
    r".*alembic\.ini$",
    r".*core/(config|secrets)\.py$",
    r".*settings/(production|secrets)\.py$",
    r".*\.env.*",
    r".*package-lock\.json$",
    r".*poetry\.lock$",
    r".*pnpm-lock\.yaml$",
    r".*cargo\.lock$",
]

COMMON_STOPWORDS = {
    "app", "src", "lib", "test", "tests", "file", "files", "code", "repo", "add",
    "the", "for", "with", "and", "into", "from", "refactor", "implement", "update",
    "fix", "create", "delete", "make", "change", "module"
}

IGNORE_DIRS = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", "node_modules", "bob_sessions"}

JS_TS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}

class ScopeSynthesizer:
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).resolve()
        self.graph = nx.DiGraph()

    def _should_ignore(self, path: Path) -> bool:
        for part in path.parts:
            if part in IGNORE_DIRS:
                return True
        return False

    def _parse_js_ts_imports(self, rel_path: Path, content: str):
        patterns = [
            r"""(?:import|export)\s+(?:.*?from\s+)?['"]([^'"]+)['"]""",
            r"""require\(['"]([^'"]+)['"]\)""",
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

    def _add_python_import_edge(self, source_path: Path, module_name: str):
        target_path = Path(*module_name.split(".")).with_suffix(".py")
        if (self.repo_root / target_path).exists():
            self.graph.add_edge(source_path, target_path)
            return

        source_dir = (self.repo_root / source_path).parent
        candidate = (source_dir / Path(*module_name.split("."))).with_suffix(".py").resolve()
        if candidate.exists() and (self.repo_root == candidate or self.repo_root in candidate.parents):
            try:
                self.graph.add_edge(source_path, candidate.relative_to(self.repo_root))
            except ValueError:
                pass

    def build_dependency_graph(self) -> nx.DiGraph:
        self.graph.clear()
        source_files = [
            f for f in self.repo_root.rglob("*")
            if f.is_file() and (f.suffix == ".py" or f.suffix in JS_TS_EXTENSIONS)
            and not self._should_ignore(f.relative_to(self.repo_root))
        ]
        
        for file_path in source_files:
            rel_path = file_path.relative_to(self.repo_root)
            self.graph.add_node(rel_path)
            
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if file_path.suffix == ".py":
                    tree = ast.parse(content)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                self._add_python_import_edge(rel_path, alias.name)
                        elif isinstance(node, ast.ImportFrom) and node.module:
                            self._add_python_import_edge(rel_path, node.module)
                elif file_path.suffix in JS_TS_EXTENSIONS:
                    self._parse_js_ts_imports(rel_path, content)
            except Exception:
                continue
                
        return self.graph

    def synthesize_scope(self, task_prompt: str) -> ScopeContract:
        self.build_dependency_graph()
        permitted: Set[Path] = set()
        restricted: Set[Path] = set()

        # Identify sensitive files
        for p in self.repo_root.rglob("*"):
            if p.is_file():
                rel = p.relative_to(self.repo_root)
                if self._should_ignore(rel):
                    continue
                rel_str = str(rel)
                if any(re.match(pattern, rel_str) for pattern in KNOWN_SENSITIVE_PATTERNS):
                    restricted.add(rel)

        # 1. Check explicit path mentions in prompt
        seed_nodes: List[Path] = []
        for node in self.graph.nodes:
            if str(node) in task_prompt or (node.stem in task_prompt and node.stem not in COMMON_STOPWORDS):
                seed_nodes.append(node)

        # 2. If no explicit path, match non-stopword keywords
        if not seed_nodes:
            keywords = [
                kw for kw in re.findall(r"\b[a-zA-Z]{3,}\b", task_prompt.lower())
                if kw not in COMMON_STOPWORDS
            ]
            for node in self.graph.nodes:
                node_str = str(node).lower()
                if any(kw in node_str for kw in keywords):
                    seed_nodes.append(node)

        # Add 1-hop reachable nodes to permitted scope
        for seed in seed_nodes:
            if seed not in restricted:
                permitted.add(seed)
                for neighbor in self.graph.successors(seed):
                    if neighbor not in restricted:
                        permitted.add(neighbor)

        # If empty seeds, default permitted to all non-restricted py files in graph
        if not permitted:
            for node in self.graph.nodes:
                if node not in restricted:
                    permitted.add(node)

        return ScopeContract(
            permitted_paths=permitted,
            restricted_paths=restricted,
            task_intent=task_prompt
        )
