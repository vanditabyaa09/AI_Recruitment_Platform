import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings

settings = get_settings()


class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self.jd_collection = self.client.get_or_create_collection("job_descriptions")
        self.cv_collection = self.client.get_or_create_collection("candidates")

    def upsert_jd(self, jd_id: str, embedding: list[float], metadata: dict):
        self.jd_collection.upsert(
            ids=[jd_id],
            embeddings=[embedding],
            metadatas=[{k: str(v)[:500] for k, v in metadata.items()}],
        )

    def get_jd_embedding(self, jd_id: str) -> list[float] | None:
        """Return a previously stored JD embedding so ranking can reuse it
        instead of paying to embed the same JD again."""
        try:
            res = self.jd_collection.get(ids=[jd_id], include=["embeddings"])
            embeddings = res.get("embeddings") if res else None
            if embeddings is not None and len(embeddings) > 0:
                emb = embeddings[0]
                return list(emb) if emb is not None else None
        except Exception:
            pass
        return None

    def upsert_cv(self, candidate_id: str, embedding: list[float], metadata: dict):
        self.cv_collection.upsert(
            ids=[candidate_id],
            embeddings=[embedding],
            metadatas=[{k: str(v)[:500] for k, v in metadata.items()}],
        )

    def query_similar_cvs(self, jd_embedding: list[float], n: int = 10) -> list[dict]:
        if self.cv_collection.count() == 0:
            return []
        results = self.cv_collection.query(query_embeddings=[jd_embedding], n_results=min(n, self.cv_collection.count()))
        items = []
        if results and results["ids"]:
            for i, cid in enumerate(results["ids"][0]):
                dist = results["distances"][0][i] if results.get("distances") else 0
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                items.append({"id": cid, "distance": dist, "metadata": meta})
        return items


vector_store = VectorStore()
