# Step 5: Semantic Search
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings
from pymilvus import MilvusClient

# Connect to existing database
client = MilvusClient('/tmp/knowledge.db')
embedder = NVIDIAEmbeddings(base_url="http://nim-proxy.labs.svc:8080/v1", model="nvidia/nv-embedqa-e5-v5", api_key="not-needed")

# TODO: Define a query
query = "What is NeMo Agent Toolkit?"

# TODO: Embed the query using embed_query() (NOT embed_documents())
query_vector = embedder.embed_query(query)

# Search Milvus
results = client.search(
    collection_name="knowledge",
    data=[query_vector],           # Can search multiple queries at once
    limit=3,                       # Return top 3 results
    output_fields=["text", "source"]  # Which metadata to return
)

print(f'Query: "{query}"\n')
print(f'Top {len(results[0])} results:')
for i, hit in enumerate(results[0]):
    score = hit['distance']
    text = hit['entity']['text']
    source = hit['entity']['source']
    print(f'  {i+1}. [{score:.3f}] ({source}) {text[:100]}...')

client.close()
