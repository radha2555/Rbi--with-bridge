import os
import warnings
import logging
import tempfile
import requests
from fastapi import FastAPI, HTTPException, Request # Import Request
from fastapi.responses import JSONResponse # Import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_community.vectorstores import Chroma
from langchain.chains import RetrievalQA
from googlesearch import search as google_search
from pydantic import BaseModel
import time
import signal # Import signal module
import sys # Import sys module

# Disable warnings for a cleaner console output
warnings.filterwarnings("ignore")
logging.getLogger("transformers").setLevel(logging.ERROR)

# Configuration for document paths and ChromaDB persistence
# IMPORTANT: These paths are relative to the directory where the FastAPI app is run.
# Ensure your 'backend' directory (containing D1. Master Circulars and data) is correctly structured.
DOCUMENTS_FOLDER = "D1. Master Circulars"  # Folder containing the 33 PDF files
DATA_DOCUMENTS_FOLDER = "data"  # New folder for data documents
PERSIST_DIRECTORY = "chroma_db"  # Where to store ChromaDB data for policy documents
DATA_PERSIST_DIRECTORY = "data_chroma_db"  # New directory for data vectorstore

app = FastAPI()

# Configure CORS to allow requests from your React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Be more specific in production, e.g., ["http://localhost:3000"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QuestionRequest(BaseModel):
    question: str

def print_progress(current, total, stage):
    """Helper function to print progress updates"""
    progress = (current / total) * 100
    print(f"\r[{stage}] Progress: {current}/{total} ({progress:.1f}%)", end="")
    if current == total:
        print()  # New line when complete

def load_documents_from_folder(folder_path):
    """Load all PDF documents from the specified folder with progress tracking"""
    documents = []
    if not os.path.exists(folder_path):
        print(f"Warning: Documents folder not found: {folder_path}. Skipping document loading for this path.")
        return []
    
    file_list = [f for f in os.listdir(folder_path) if f.lower().endswith('.pdf')]
    total_files = len(file_list)
    print(f"\nFound {total_files} PDF files to process in {folder_path}")
    
    for i, file_name in enumerate(file_list, 1):
        file_path = os.path.join(folder_path, file_name)
        try:
            start_time = time.time()
            print(f"\nProcessing file {i}/{total_files}: {file_name}")
            
            loader = PyPDFLoader(file_path)
            pages = loader.load_and_split()
            
            for page_num, page in enumerate(pages, 1):
                page.metadata["source"] = file_name
                page.metadata["page"] = page_num
            
            documents.extend(pages)
            elapsed = time.time() - start_time
            print(f"Processed {len(pages)} pages in {elapsed:.1f} seconds")
            
            print_progress(i, total_files, "LOADING")
            
        except Exception as e:
            print(f"\nError loading {file_name}: {str(e)}")
            continue
    
    print(f"\nTotal documents loaded: {len(documents)}")
    return documents

def get_vectorstore():
    try:
        # Check if we have a persisted ChromaDB for policy documents
        if os.path.exists(PERSIST_DIRECTORY) and os.listdir(PERSIST_DIRECTORY):
            print("\nLoading existing Policy ChromaDB from disk...")
            start_time = time.time()
            embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L12-v2')
            vectorstore = Chroma(persist_directory=PERSIST_DIRECTORY, embedding_function=embeddings)
            elapsed = time.time() - start_time
            print(f"Loaded Policy ChromaDB in {elapsed:.1f} seconds")
            return vectorstore, None
        
        # Load and process documents if no persisted DB is found
        print("\nNo existing Policy ChromaDB found. Creating new vectorstore...")
        start_time = time.time()
        
        print("\nStep 1/3: Loading PDF documents for Policy")
        documents = load_documents_from_folder(DOCUMENTS_FOLDER)
        if not documents:
            return None, "No valid policy documents found in the folder"
            
        print("\nStep 2/3: Splitting policy documents into chunks")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=3000,
            chunk_overlap=500,
            separators=["\n\n", "\n•", "\n", " ", ""]
        )
        
        split_documents = text_splitter.split_documents(documents)
        print(f"Created {len(split_documents)} policy document chunks")
        
        print("\nStep 3/3: Creating policy vectorstore (this may take several minutes)")
        embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L12-v2')
        
        # Process in batches to show progress
        batch_size = 100
        total_batches = (len(split_documents) + batch_size - 1) // batch_size
        vectorstore = None
        
        for batch_num in range(total_batches):
            batch_start = batch_num * batch_size
            batch_end = (batch_num + 1) * batch_size
            batch_docs = split_documents[batch_start:batch_end]
            
            print(f"\rProcessing policy batch {batch_num + 1}/{total_batches}", end="")
            
            if vectorstore is None:
                vectorstore = Chroma.from_documents(
                    documents=batch_docs,
                    embedding=embeddings,
                    persist_directory=PERSIST_DIRECTORY
                )
            else:
                vectorstore.add_documents(batch_docs)
        
        vectorstore.persist()
        elapsed = time.time() - start_time
        print(f"\nPolicy Vectorstore creation complete in {elapsed:.1f} seconds")
        print(f"Total policy documents indexed: {len(split_documents)}")
        
        return vectorstore, None

    except Exception as e:
        print(f"\nError in get_vectorstore: {str(e)}")
        return None, f"Error processing policy documents: {str(e)}"

def get_data_vectorstore():
    try:
        # Check if we have a persisted Data ChromaDB
        if os.path.exists(DATA_PERSIST_DIRECTORY) and os.listdir(DATA_PERSIST_DIRECTORY):
            print("\nLoading existing Data ChromaDB from disk...")
            start_time = time.time()
            embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L12-v2')
            vectorstore = Chroma(persist_directory=DATA_PERSIST_DIRECTORY, embedding_function=embeddings)
            
            # Print collection stats for debugging
            collection = vectorstore._collection
            print(f"Data vectorstore contains {collection.count()} chunks")
            
            elapsed = time.time() - start_time
            print(f"Loaded Data ChromaDB in {elapsed:.1f} seconds")
            return vectorstore, None
        
        # Load and process data documents with optimized settings
        print("\nNo existing Data ChromaDB found. Creating new data vectorstore...")
        start_time = time.time()
        
        print("\nStep 1/3: Loading Data documents with optimized settings")
        documents = []
        file_list = [f for f in os.listdir(DATA_DOCUMENTS_FOLDER) if f.lower().endswith('.pdf')]
        
        # Define splitters outside the loop
        large_file_splitter = RecursiveCharacterTextSplitter(
            chunk_size=5000,  # Bigger chunks for large files
            chunk_overlap=1000,
            separators=["\n\n\n", "\n\n", "\n•", "\n", " "]
        )
        regular_splitter = RecursiveCharacterTextSplitter(
            chunk_size=3000,
            chunk_overlap=500,
            separators=["\n\n", "\n•", "\n", " ", ""]
        )
        
        for file_name in file_list:
            file_path = os.path.join(DATA_DOCUMENTS_FOLDER, file_name)
            file_size = os.path.getsize(file_path)
            
            print(f"\nProcessing {file_name} (size: {file_size/1_000_000:.1f}MB)")
            
            loader = PyPDFLoader(file_path)
            pages = loader.load_and_split()
            
            # Choose splitter based on file size or name
            if file_size > 50_000_000 or "84530aasb-gnab2025-b.pdf" in file_name.lower():
                print("Using large file optimization settings")
                splits = large_file_splitter.split_documents(pages)
            else:
                splits = regular_splitter.split_documents(pages)
            
            print(f"Generated {len(splits)} chunks from {file_name}")
            documents.extend(splits)
        
        if not documents:
            return None, "No valid data documents found in the folder"
        
        print("\nStep 2/3: Creating optimized data vectorstore")
        embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L12-v2')
        
        # Use larger batch size for faster processing
        batch_size = 200
        total_batches = (len(documents) + batch_size - 1) // batch_size
        vectorstore = None
        
        for batch_num in range(total_batches):
            batch_start = batch_num * batch_size
            batch_end = (batch_num + 1) * batch_size
            batch_docs = documents[batch_start:batch_end]
            
            print(f"\rProcessing data batch {batch_num + 1}/{total_batches}", end="")
            
            if vectorstore is None:
                vectorstore = Chroma.from_documents(
                    documents=batch_docs,
                    embedding=embeddings,
                    persist_directory=DATA_PERSIST_DIRECTORY
                )
            else:
                vectorstore.add_documents(batch_docs)
        
        vectorstore.persist()
        elapsed = time.time() - start_time
        print(f"\nData Vectorstore creation complete in {elapsed:.1f} seconds")
        print(f"Total data chunks indexed: {len(documents)}")
        
        return vectorstore, None

    except Exception as e:
        print(f"\nError in get_data_vectorstore: {str(e)}")
        return None, f"Error processing data documents: {str(e)}"
    
# Initialize vectorstores at startup
print("Starting server initialization (loading/creating vector stores)...")
start_time = time.time()
vectorstore, vectorstore_error = get_vectorstore()
data_vectorstore, data_vectorstore_error = get_data_vectorstore()
elapsed = time.time() - start_time
print(f"\nServer initialization completed in {elapsed:.1f} seconds")

# --- Health Check Endpoint ---
@app.get("/health")
async def health_check():
    """Endpoint for the Node.js proxy to check if FastAPI is alive and responsive."""
    return JSONResponse({"status": "ok", "message": "FastAPI is running"})

# --- Shutdown Endpoint ---
@app.post("/shutdown")
async def shutdown():
    """
    Endpoint to gracefully shut down the FastAPI server.
    This is called by the Node.js proxy.
    """
    print("Received shutdown request. Initiating graceful shutdown of FastAPI server...")
    # It's good practice to add any cleanup logic here (e.g., close DB connections)
    
    # Use os.kill to send a SIGINT signal to the current process,
    # which uvicorn will catch to shut down gracefully.
    os.kill(os.getpid(), signal.SIGINT)
    # The return here might not always be sent before the process exits,
    # but it provides an immediate response if the shutdown is asynchronous.
    return JSONResponse({"message": "FastAPI server is shutting down."})


@app.post("/api/policy-answer")
async def get_policy_answer(request: QuestionRequest):
    try:
        global vectorstore, vectorstore_error
        
        if vectorstore_error:
            return {"answer": vectorstore_error}
            
        if vectorstore is None:
            return {"answer": "Failed to process documents. Please check the document paths."}

        print(f"\nProcessing policy question: {request.question}")
        start_time = time.time()
        
        template = """You are an expert on RBI banking regulations. Answer the question based only on the following context:
        {context}

        Question: {question}

        Provide a concise answer with relevant RBI guidelines. 
        DO NOT mention any document names, circular numbers, or paragraph references.
        Only provide the regulatory information in clear, simple language.
        If you don't know, say "I couldn't find this information in the documents"."""
        
        prompt_template = ChatPromptTemplate.from_template(template)

        # Consider using environment variables for API keys in production
        os.environ["GROQ_API_KEY"] = "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"
        llm = ChatGroq(model_name="llama3-8b-8192", temperature=0.1)

        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=vectorstore.as_retriever(search_kwargs={'k': 6}),
            chain_type_kwargs={"prompt": prompt_template},
            return_source_documents=False 
        )

        print("Searching policy documents...")
        result = qa_chain({"query": request.question})
        
        # Clean the response to remove any remaining references
        response = result["result"]
        response = response.replace("According to RBI guidelines", "The regulations state")
        response = response.replace("as per", "")
        response = response.replace("per", "")
        
        elapsed = time.time() - start_time
        print(f"Policy question processed in {elapsed:.1f} seconds")
        
        return {"answer": response}

    except Exception as e:
        print(f"Error processing policy question: {str(e)}")
        # Provide a more generic error message to the frontend for security/user experience
        return {"answer": f"An error occurred while getting policy answer: {str(e)}"}
    
@app.post("/api/data-answer")
async def get_data_answer(request: QuestionRequest):
    try:
        global data_vectorstore, data_vectorstore_error
        
        if data_vectorstore_error:
            return {"answer": data_vectorstore_error}
            
        if data_vectorstore is None:
            return {"answer": "Failed to process data documents. Please check the document paths."}

        print(f"\nProcessing data question: {request.question}")
        timer = {}
        start_time = time.time()
        
        # Phase 1: Document retrieval
        timer['retrieval_start'] = time.time()
        retriever = data_vectorstore.as_retriever(
            search_kwargs={
                'k': 4,  # Reduced from 6 to improve speed
            }
        )
        timer['retrieval_end'] = time.time()
        
        # Phase 2: LLM processing
        timer['llm_start'] = time.time()
        template = """You are an expert on banking data and statistics. Answer the question based only on the following context:
        {context}

        Question: {question}

        Provide a concise answer with relevant data points.
        DO NOT mention any document names, report titles, or page references.
        Present the data in clear, simple language without citations.
        If you don't know, say "I couldn't find this information in the data documents"."""
        
        prompt_template = ChatPromptTemplate.from_template(template)

        # Consider using environment variables for API keys in production
        os.environ["GROQ_API_KEY"] = "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"
        llm = ChatGroq(model_name="llama3-8b-8192", temperature=0.1)

        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever,
            chain_type_kwargs={
                "prompt": prompt_template,
                "verbose": False  # For debugging
            },
            return_source_documents=False
        )

        result = qa_chain({"query": request.question})
        timer['llm_end'] = time.time()
        
        # Clean and format the response
        response = result["result"]
        response = response.replace("Based on the data", "The available information shows")
        response = response.replace("according to", "")
        
        elapsed = time.time() - start_time
        
        # Print detailed timing
        print(f"Data question processed in {elapsed:.1f} seconds")
        
        return {"answer": response}

    except Exception as e:
        print(f"Error processing data question: {str(e)}")
        # Provide a more generic error message to the frontend for security/user experience
        return {"answer": f"An error occurred while getting data answer: {str(e)}"}

@app.post("/api/web-answer")
async def get_web_answer(request: QuestionRequest):
    try:
        # Consider using environment variables for API keys in production
        os.environ["GROQ_API_KEY"] = "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"
        llm = ChatGroq(model_name="llama3-8b-8192", temperature=0.5)
        
        # Google Custom Search API configuration
        # Consider using environment variables for API keys in production
        GOOGLE_API_KEY = "AIzaSyAx68FS8TKfDM4QptiFmE_2GUauVevP9o8"  # Replace with your actual key
        SEARCH_ENGINE_ID = "72bcbdff4fedf426f"  # Replace with your CX
        
        def google_custom_search(query, num=3):
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                'q': query,
                'key': GOOGLE_API_KEY,
                'cx': SEARCH_ENGINE_ID,
                'num': num
            }
            try:
                response = requests.get(url, params=params)
                response.raise_for_status()
                return response.json().get('items', [])
            except Exception as e:
                print(f"Google API error: {e}")
                return []

        # Improved link gathering
        links_section = "🔗 Relevant Links from Across the Web:\n\n"
        search_queries = [
            f"{request.question} RBI regulations",
            f"banking regulations {request.question}",
            f"{request.question} financial policies",
            f"latest updates on {request.question} banking",
            f"{request.question} financial authority guidelines"
        ]
        
        seen_urls = set()
        total_links = 0
        max_links = 3
        
        for query in search_queries:
            if total_links >= max_links:
                break
            try:
                results = google_custom_search(query)
                for result in results:
                    if total_links >= max_links:
                        break
                    if result.get('link') and result.get('link') not in seen_urls:
                        seen_urls.add(result.get('link'))
                        total_links += 1
                        summary = llm.invoke(
                            f"Create a concise 1-2 sentence summary of this page for someone researching '{request.question}':\n"
                            f"Title: {result.get('title', 'N/A')}\n"
                            f"Snippet: {result.get('snippet', 'No description')}"
                        ).content
                        links_section += f"• {result.get('title', 'Untitled')}\n  URL: {result.get('link')}\n  {summary}\n\n"
            except Exception as e:
                print(f"Error processing query '{query}': {e}")
                continue
        
        return {"answer": links_section.strip()}
    
    except Exception as e:
        print(f"Error generating web answer: {str(e)}")
        # Provide a more generic error message to the frontend for security/user experience
        return {"answer": f"An error occurred while getting web answer: {str(e)}"}
            
@app.post("/api/combined-answer")
async def get_combined_answer(request: QuestionRequest):
    """
    Combines answers from policy documents, web search, and data documents.
    Note: Your React frontend currently makes separate calls to each API.
    This combined endpoint is provided for completeness if you decide to change
    your frontend logic to make a single call.
    """
    policy_answer = await get_policy_answer(request)
    web_answer = await get_web_answer(request)
    data_answer = await get_data_answer(request)
    return {
        "policy_answer": policy_answer["answer"],
        "web_answer": web_answer["answer"],
        "data_answer": data_answer["answer"]
    }

# This block allows you to run the FastAPI application directly for testing
# However, in your integrated setup, the Node.js proxy will be responsible
# for spawning and managing this FastAPI process.
if __name__ == "__main__":
    import uvicorn
    print("\nStarting FastAPI server directly (for testing purposes)...")
    uvicorn.run(app, host="0.0.0.0", port=8000)