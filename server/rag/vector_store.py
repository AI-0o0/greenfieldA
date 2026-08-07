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

if __name__ == "__main__":
    initialize_vector_db()
