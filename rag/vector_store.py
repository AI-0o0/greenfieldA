import os
import chromadb
from sentence_transformers import SentenceTransformer

# Initialize Local Vector Store with Persistent Directory
VECTOR_DB_DIR = os.path.join(os.path.dirname(__file__), "vector_store_data")
client = chromadb.PersistentClient(path=VECTOR_DB_DIR)

# HNSW ANN Index Collection with Metadata filtering capabilities
collection = client.get_or_create_collection(
    name="greenfield_knowledge",
    metadata={"hnsw:space": "cosine"} # HNSW ANN Index
)

# Local Embedding Model (Free & Fast)
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

def get_embedding(text: str) -> list[float]:
    return embedding_model.encode(text).tolist()

def initialize_vector_db():
    """Reads docs, chunks them, generates embeddings, and stores in ChromaDB with metadata."""
    docs_dir = os.path.join(os.path.dirname(__file__), "docs")
    if not os.path.exists(docs_dir):
        return

    documents = []
    metadatas = []
    ids = []

    doc_id_counter = 0
    for file_name in os.listdir(docs_dir):
        if file_name.endswith(".txt"):
            file_path = os.path.join(docs_dir, file_name)
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Basic Chunking by sections
            chunks = content.split("\n\n")
            for chunk in chunks:
                if chunk.strip():
                    doc_id_counter += 1
                    documents.append(chunk.strip())
                    metadatas.append({"source": file_name, "chunk_id": doc_id_counter})
                    ids.append(f"doc_chunk_{doc_id_counter}")

    if documents:
        embeddings = [get_embedding(doc) for doc in documents]
        collection.upsert(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        print(f"[RAG Vector DB]: Initialized with {len(documents)} chunks.")


# ==============================================================
# Runtime document management (platform admin surface)
#
# These operate on the SAME live Chroma collection instance the
# retrievers query, so an admin's add/remove is reflected in what
# the Memory/RAG agent retrieves on its very next query — not just
# written to storage and ignored.
# ==============================================================

def _chunk_text(text: str) -> list[str]:
    return [c.strip() for c in text.split("\n\n") if c.strip()]


def list_documents() -> list[dict]:
    """Groups stored chunks by source document with chunk counts."""
    got = collection.get(include=["metadatas"])
    counts: dict[str, int] = {}
    for meta in got.get("metadatas", []):
        source = (meta or {}).get("source", "unknown")
        counts[source] = counts.get(source, 0) + 1
    return [
        {"source": source, "chunks": n}
        for source, n in sorted(counts.items())
    ]


def add_document(source_name: str, text: str) -> dict:
    """
    Ingests (or atomically replaces) one document into the live vector store.
    Chunks on blank lines exactly like initialize_vector_db, embeds locally,
    and upserts with deterministic per-source chunk ids so re-adding the same
    source never duplicates.
    """
    chunks = _chunk_text(text)
    if not chunks:
        raise ValueError(f"Document '{source_name}' produced no usable chunks.")

    # Replace-any-existing semantics: drop old chunks for this source first.
    delete_document(source_name)

    embeddings = [get_embedding(chunk) for chunk in chunks]
    safe_source = "".join(c if c.isalnum() or c in "-_." else "_" for c in source_name)
    collection.upsert(
        documents=chunks,
        embeddings=embeddings,
        metadatas=[{"source": source_name, "chunk_id": i + 1} for i in range(len(chunks))],
        ids=[f"doc::{safe_source}::chunk_{i}" for i in range(len(chunks))],
    )
    return {"source": source_name, "chunks_added": len(chunks)}


def delete_document(source_name: str) -> int:
    """Removes every chunk belonging to a source from the live vector store."""
    got = collection.get(where={"source": source_name}, include=[])
    ids = got.get("ids", [])
    if ids:
        collection.delete(ids=ids)
    return len(ids)


if __name__ == "__main__":
    initialize_vector_db()
