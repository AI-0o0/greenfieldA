from rank_bm25 import BM25Okapi
from langchain.chat_models import init_chat_model
from .vector_store import collection, get_embedding
from dotenv import load_dotenv
from config import MODEL_NAME, MODEL_PROVIDER

load_dotenv()
llm = init_chat_model(model=MODEL_NAME, model_provider=MODEL_PROVIDER)

# 1. Naive RAG
def naive_rag_search(query: str, top_k: int = 3, source_doc: str = None) -> list[str]:
    query_vector = get_embedding(query)
    # Apply metadata pre-filtering
    where_clause = {"source": source_doc} if source_doc else None
    
    results = collection.query(
        query_embeddings=[query_vector], 
        n_results=top_k,
        where=where_clause
    )
    return results["documents"][0] if results["documents"] else []

# 2. Hybrid Search (Vector + BM25 Keyword Search)
def hybrid_search(query: str, top_k: int = 3) -> list[str]:
    # Fetch all docs for BM25 indexing
    all_data = collection.get()
    docs = all_data["documents"]
    if not docs:
        return []

    # Tokenization for BM25
    tokenized_corpus = [doc.lower().split() for doc in docs]
    bm25 = BM25Okapi(tokenized_corpus)
    bm25_scores = bm25.get_scores(query.lower().split())
    
    # Vector Search
    vector_docs = naive_rag_search(query, top_k=top_k)
    
    # BM25 Search
    top_bm25_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:top_k]
    bm25_docs = [docs[i] for i in top_bm25_indices]

    # Deduplicate and combine (Hybrid)
    combined = list(dict.fromkeys(vector_docs + bm25_docs))
    return combined[:top_k]

# 3. Agentic RAG (Multi-hop Retrieval Loop)
def agentic_rag_search(query: str) -> list[str]:
    retrieved_chunks = []
    current_query = query

    for turn in range(2): # Max 2 hops
        chunks = hybrid_search(current_query, top_k=2)
        retrieved_chunks.extend(chunks)

        # Agent decides if it needs more information
        check_prompt = f"""Given the query: '{query}' and retrieved info: {retrieved_chunks}.
Is this sufficient to fully answer? If YES, write 'DONE'. If NO, write a short new search query for the missing detail."""
        res = llm.invoke(check_prompt).content.strip()
        if "DONE" in res or res == current_query:
            break
        current_query = res

    return list(set(retrieved_chunks))
