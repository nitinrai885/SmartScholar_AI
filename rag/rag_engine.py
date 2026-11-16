"""
RAG engine: chunk the rubric, embed it, store it in ChromaDB, and answer similarity searches.

Pipeline:  rubric text -> chunks (one per clause) -> embeddings (Sentence Transformers)
           -> ChromaDB collection -> retrieve(query) returns the most similar clauses.

If ChromaDB / Sentence Transformers cannot be loaded (for example no internet on the
very first run, so the embedding model cannot be downloaded) the engine falls back to
a simple keyword search over the same chunks. `engine.mode` always says which one is active.
"""
import re
from pathlib import Path

import config


def load_rubric_chunks(path=config.RUBRIC_PATH):
    """Document chunking: every '[ID] text' clause becomes one chunk with its section name."""
    chunks, section, current = [], "", None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("SECTION:"):
            section, current = line.replace("SECTION:", "").strip(), None
        elif not line:
            current = None                                   # a blank line ends the clause
        else:
            match = re.match(r"^\[([A-Z]+-\d+)\]\s*(.*)$", line)
            if match:
                current = {"clause_id": match.group(1), "section": section, "text": match.group(2)}
                current["title"] = current["text"].split(".")[0]
                chunks.append(current)
            elif current is not None:
                current["text"] += " " + line                # clause continues on the next line
    return chunks


def select_references(retrieved_chunks, applied_clause_ids):
    """Rubric references = only clauses that were RETRIEVED and were actually APPLIED."""
    rubric_order = [c["clause_id"] for c in load_rubric_chunks()]      # show them in rubric order
    chosen = [c for c in retrieved_chunks if c["clause_id"] in applied_clause_ids]
    chosen.sort(key=lambda c: rubric_order.index(c["clause_id"]) if c["clause_id"] in rubric_order else 999)
    return [{"clause_id": c["clause_id"], "section": c["section"], "title": c["title"]} for c in chosen]


class RagEngine:
    def __init__(self, rubric_path=config.RUBRIC_PATH):
        self.chunks = load_rubric_chunks(rubric_path)
        if not self.chunks:
            raise ValueError(f"No rubric clauses found in {rubric_path}. "
                             "Each clause must start with an id such as [ELG-1].")
        self.by_id = {c["clause_id"]: c for c in self.chunks}
        self.mode = "keyword-fallback"
        self.fallback_reason = ""
        self.model = None
        self.collection = None
        self._build_vector_store()

    def _build_vector_store(self):
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(config.EMBEDDING_MODEL)
            client = chromadb.Client()                       # in-memory vector store
            self.collection = client.get_or_create_collection("scholarship_rubric")
            texts = [f"{c['section']}: {c['text']}" for c in self.chunks]
            self.collection.upsert(
                ids=[c["clause_id"] for c in self.chunks],
                documents=texts,
                embeddings=self.model.encode(texts).tolist(),
                metadatas=[{"clause_id": c["clause_id"], "section": c["section"]} for c in self.chunks],
            )
            self.mode = "chromadb+sentence-transformers"
        except Exception as error:                           # keep the project usable offline
            self.model = None
            self.collection = None
            self.fallback_reason = f"{type(error).__name__}: {error}"

    def retrieve(self, query, sections=None, n_results=5):
        """Similarity search. `sections` limits the search to some rubric sections."""
        pool = [c for c in self.chunks if not sections or c["section"] in sections]
        n = min(n_results, len(pool))
        if n == 0:
            return []
        if self.collection is not None:
            where = {"section": {"$in": list(sections)}} if sections else None
            found = self.collection.query(query_embeddings=self.model.encode([query]).tolist(),
                                          n_results=n, where=where)
            results = []
            for meta, distance in zip(found["metadatas"][0], found["distances"][0]):
                chunk = dict(self.by_id[meta["clause_id"]])
                chunk["distance"] = round(float(distance), 4)
                results.append(chunk)
            return results
        return self._keyword_search(query, pool, n)

    def _keyword_search(self, query, pool, n):
        words = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2}
        scored = []
        for chunk in pool:
            chunk_words = set(re.findall(r"[a-z0-9]+", (chunk["title"] + " " + chunk["text"]).lower()))
            scored.append((len(words & chunk_words), chunk))
        scored.sort(key=lambda pair: -pair[0])               # stable: ties keep rubric order
        return [dict(chunk, distance=None) for _, chunk in scored[:n]]
