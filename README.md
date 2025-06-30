# ⚖️ RBI Legal Chatbot

An AI chatbot built for **automated legal query answering** related to RBI Acts, Rules, and Case Laws.

> Powered by **LangChain**, **ChromaDB**, **FastAPI**, and a **React frontend** — all orchestrated by a **Node.js proxy** with backend auto-management.

---

## 🧩 Key Components

| Layer         | Tech Stack                    | Purpose                               |
| ------------- | ----------------------------- | ------------------------------------- |
| Data          | PDFs (Acts, Rules, Case Laws) | Source of legal documents             |
| Embedding     | HuggingFace + Chroma          | Vector search on legal text           |
| Backend       | FastAPI (`main.py`)           | Serves legal answers via LangChain    |
| Orchestration | Node.js (`server.js`)         | Manages FastAPI auto-start/shutdown   |
| Frontend      | React (`IBChatbot.js`)        | Chat-based UI for querying legal data |

---

## 🔧 Quick Start

### 1. Setup Backend

```bash
# Setup Python packages
pip install -r requirements.txt

# Load PDFs into Chroma vectorstore
python backend/diffchroma.py
```

> No need to download data — everything is in the `data/` folder.

---

### 2. Start Proxy Server (Auto-runs backend)

```bash
npm install
node server.js
```

This runs the Node.js server on `localhost:3001` and:

* Starts `main.py` via `start_fastapi.bat` or `.sh`
* Shuts it down after 2 minutes of inactivity

---

### 3. Launch Frontend

```bash
cd frontend
npm install
npm start
```

Access the chatbot at: [http://localhost:3000](http://localhost:3000)

---

## 🛠 Core Features

✅ Answers legal questions using RBI laws & judgments
🔁 FastAPI backend managed automatically
📚 Multi-source: Acts, Rules, SC, HC, NCLT, NCLAT
🖥️ Rich React UI with notes, clipboard, and download
🧠 Runs on Groq or any compatible LLM backend

---

## 📂 Repo Layout

```
RBI-catbot-main/
├── main.py             # FastAPI backend
│── start_fastapi.bat   # Startup script (Windows)
├── data/                   # All legal PDFs
├── server.js               # Node.js proxy (backend controller)
├── frontend/               # React chatbot interface
└── README.md
```

---

