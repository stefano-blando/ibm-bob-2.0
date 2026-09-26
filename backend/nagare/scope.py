import ast
import re
from pathlib import Path
from typing import Set, Dict, List
import networkx as nx
from nagare.models import ScopeContract

KNOWN_SENSITIVE_PATTERNS = [
    r".*database/schema\.sql$",
    r".*database/migrations/.*",
    r".*core/config\.py$",
    r".*core/secrets.*",
    r".*\.env.*",
    r".*package-lock\.json$",
    r".*poetry\.lock$",
]

IGNORE_DIRS = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", "node_modules", "bob_sessions"}

class ScopeSynthesizer:
    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root).resolve()
        self.graph = nx.DiGraph()

    def _should_ignore(self, path: Path) -> bool:
        for part in path.parts:
            if part in IGNORE_DIRS:
                return True
        return False

    def build_dependency_graph(self) -> nx.DiGraph:
        self.graph.clear()
        py_files = [
            f for f in self.repo_root.rglob("*.py")
            if not self._should_ignore(f.relative_to(self.repo_root))
        ]
        
        for file_path in py_files:
            rel_path = file_path.relative_to(self.repo_root)
            self.graph.add_node(rel_path)
            
            try:
                tree = ast.parse(file_path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self._add_import_edge(rel_path, alias.name)
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        self._add_import_edge(rel_path, node.module)
            except Exception:
                continue
                
        return self.graph

    def _add_import_edge(self, source_path: Path, module_name: str):
        target_path = Path(*module_name.split(".")).with_suffix(".py")
        if (self.repo_root / target_path).exists():
            self.graph.add_edge(source_path, target_path)

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

        # Match prompt keywords to seed files
        keywords = re.findall(r"\b[a-zA-Z]{3,}\b", task_prompt.lower())
        seed_nodes: List[Path] = []
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
