"""
tools/ingest_policies.py
Reads all PDF/TXT files from data/policies/, chunks them,
embeds with multilingual sentence-transformers, and upserts into Pinecone.

Usage:
    python tools/ingest_policies.py
    python tools/ingest_policies.py --force
"""
import os
import sys
import argparse

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec
from config import cfg


DEPT_KEYWORDS = {
    "exam":      ["exam", "atkt", "result", "revaluation", "hall"],
    "admin":     ["admin", "fee", "admission", "attendance", "fines"],
    "placement": ["placement", "helpdesk", "grievance", "internship"],
    "library":   ["library", "book", "borrow"],
    "hostel":    ["hostel", "room", "mess"],
}


def _detect_department(filename: str) -> str:
    name_lower = filename.lower()
    for dept, keywords in DEPT_KEYWORDS.items():
        if any(kw in name_lower for kw in keywords):
            return dept
    return "general"


def load_documents(policies_dir: str):
    docs = []
    for fname in sorted(os.listdir(policies_dir)):
        fpath = os.path.join(policies_dir, fname)
        if not os.path.isfile(fpath):
            continue
        ext = fname.lower().split(".")[-1]
        try:
            if ext == "pdf":
                loader = PyPDFLoader(fpath)
            elif ext == "txt":
                loader = TextLoader(fpath, encoding="utf-8")
            else:
                continue
            raw_docs   = loader.load()
            department = _detect_department(fname)
            for doc in raw_docs:
                doc.metadata["source"]     = fname
                doc.metadata["department"] = department
            docs.extend(raw_docs)
            print(f"  Loaded: {fname} ({len(raw_docs)} section(s), dept={department})")
        except Exception as e:
            print(f"  WARNING: Could not load {fname}: {e}")
    return docs


def main(force: bool = False):
    policies_dir = (
        os.path.join(ROOT_DIR, cfg.POLICIES_DIR)
        if not os.path.isabs(cfg.POLICIES_DIR)
        else cfg.POLICIES_DIR
    )

    print(f"\n{'='*60}")
    print(f"  CampusAI Policy Ingestion Tool  (Pinecone)")
    print(f"{'='*60}")
    print(f"  Policies dir  : {policies_dir}")
    print(f"  Pinecone index: {cfg.PINECONE_INDEX}")
    print(f"  Embedding     : {cfg.EMBEDDING_MODEL}")
    print(f"{'='*60}\n")

    if not cfg.PINECONE_API_KEY:
        print("  ERROR: PINECONE_API_KEY not set in .env / environment.")
        sys.exit(1)

    if not os.path.isdir(policies_dir):
        print(f"  ERROR: Policies directory not found: {policies_dir}")
        sys.exit(1)

    # ── Connect to Pinecone & ensure index exists ────────────────────────────
    pc = Pinecone(api_key=cfg.PINECONE_API_KEY)
    existing = [idx.name for idx in pc.list_indexes()]

    if cfg.PINECONE_INDEX in existing:
        if not force:
            print(f"  Index '{cfg.PINECONE_INDEX}' already exists.")
            print("  Use --force to delete & rebuild. Exiting.\n")
            return
        else:
            print(f"  --force: deleting existing index '{cfg.PINECONE_INDEX}' ...")
            pc.delete_index(cfg.PINECONE_INDEX)
            print("  Deleted.")

    print(f"  Creating Pinecone index '{cfg.PINECONE_INDEX}' (dim=384, cosine) ...")
    pc.create_index(
        name=cfg.PINECONE_INDEX,
        dimension=384,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    print("  Index created.\n")

    # ── Load & chunk documents ────────────────────────────────────────────────
    docs = load_documents(policies_dir)
    if not docs:
        print("  ERROR: No documents found. Add .pdf or .txt files to data/policies/")
        sys.exit(1)

    print(f"\n  Loaded {len(docs)} document section(s) total.")
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=80)
    chunks   = splitter.split_documents(docs)
    print(f"  Created {len(chunks)} chunks.\n")

    # ── Embed & upsert into Pinecone ──────────────────────────────────────────
    print(f"  Loading embedding model: {cfg.EMBEDDING_MODEL}")
    embeddings = HuggingFaceEmbeddings(
        model_name=cfg.EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    print("  Upserting vectors into Pinecone ...")
    PineconeVectorStore.from_documents(
        chunks,
        embeddings,
        index_name=cfg.PINECONE_INDEX,
        pinecone_api_key=cfg.PINECONE_API_KEY,
    )

    print(f"\n  Done! {len(chunks)} chunks indexed into Pinecone '{cfg.PINECONE_INDEX}'.")
    print("  You can now run:  python main.py\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest college policies into Pinecone vector index")
    parser.add_argument("--force", action="store_true", help="Force rebuild: delete & recreate index")
    args = parser.parse_args()
    main(force=args.force)
