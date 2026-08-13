# Steps 1-3: Knowledge base + Chunking + Embeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

documents = [
    Document(page_content="NVIDIA NIM provides optimized AI model deployment as containerized microservices. NIM supports LLMs, embedding models, and vision models with an OpenAI-compatible API.", metadata={"source": "nvidia_nim.txt"}),
    Document(page_content="Retrieval Augmented Generation (RAG) enhances LLM responses by retrieving relevant context from external knowledge bases. RAG reduces hallucination and allows access to up-to-date information beyond training data.", metadata={"source": "rag_overview.txt"}),
    Document(page_content="NeMo Agent Toolkit is an open-source library for building AI agents. It supports ReAct agents, tool calling, and YAML workflow configuration with built-in evaluation and profiling.", metadata={"source": "nemo_toolkit.txt"}),
    Document(page_content="Vector databases store high-dimensional embeddings and enable fast similarity search. Milvus is an open-source vector database that supports both embedded (Milvus Lite) and distributed deployments.", metadata={"source": "vector_db.txt"}),
]

splitter = RecursiveCharacterTextSplitter(chunk_size=150, chunk_overlap=30)
chunks = splitter.split_documents(documents)

embedder = NVIDIAEmbeddings(base_url="http://nim-proxy.labs.svc:8080/v1", model="nvidia/nv-embedqa-e5-v5", api_key="not-needed")
vectors = embedder.embed_documents([c.page_content for c in chunks])
print(f'{len(vectors)} vectors ready (dim={len(vectors[0])})')

# Step 4: Store in Milvus
# TODO: Import MilvusClient from pymilvus
from pymilvus import MilvusClient

# TODO: Create a client at /tmp/knowledge.db
client = MilvusClient("/tmp/knowledge.db")  # Local file-based database

# TODO: Create a collection named 'knowledge' with dimension=1024 and auto_id=True
# Create a collection (like a table)
client.create_collection(
    collection_name="knowledge",
    dimension=1024,        # Must match your embedding dimension
    auto_id=True,          # Auto-generate IDs
)

# TODO: Insert data — each item needs: vector, text, source
data = []
for chunk, vec in zip(chunks, vectors):
    data.append({
        'vector': vec,
        'text': chunk.page_content,
        'source': chunk.metadata['source'],
    })

# TODO: Call client.insert(collection_name='knowledge', data=data)
client.insert(collection_name="knowledge", data=data)

print(f'Stored {len(data)} vectors in Milvus')
stats = client.get_collection_stats('knowledge')
print(f'Collection stats: {stats}')
