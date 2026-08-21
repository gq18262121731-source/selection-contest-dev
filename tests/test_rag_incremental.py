import sys
import os
import shutil
import time
from pathlib import Path
from io import StringIO
import contextlib

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent.langchain_rag_service import LangChainRAGService
from backend.config import Settings

def test_incremental_rag():
    # Setup temp knowledge dir
    test_dir = Path("tmp_knowledge_test")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()
    
    # Create test files
    file1 = test_dir / "test1.md"
    file1.write_text("# Test 1\nContent 1", encoding="utf-8")
    
    file2 = test_dir / "test2.md"
    file2.write_text("# Test 2\nContent 2", encoding="utf-8")
    
    # Mock settings
    settings = MagicMock(spec=Settings)
    settings.chroma_path = "tmp_chroma_test"
    settings.rag_chunk_size = 500
    settings.rag_chunk_overlap = 50
    settings.tongyi_embedding_configured = False 
    settings.qwen_enable_rerank = False
    
    if Path(settings.chroma_path).exists():
        shutil.rmtree(settings.chroma_path)
    Path(settings.chroma_path).mkdir()

    print("--- Initial Run ---")
    f = StringIO()
    with contextlib.redirect_stdout(f):
        rag = LangChainRAGService(settings, test_dir)
    output = f.getvalue()
    print(output)
    assert "0 clean chunks, 2 new chunks" in output
    print("✓ Initial run processed all files")

    print("\n--- Secondary Run (No changes) ---")
    f = StringIO()
    with contextlib.redirect_stdout(f):
        rag2 = LangChainRAGService(settings, test_dir)
    output = f.getvalue()
    print(output)
    assert "2 clean chunks, 0 new chunks" in output
    print("✓ Secondary run reused all chunks")

    print("\n--- Third Run (Modify one file) ---")
    time.sleep(1.1) 
    file1.write_text("# Test 1 updated\nContent 1 is now longer.", encoding="utf-8")
    
    f = StringIO()
    with contextlib.redirect_stdout(f):
        rag3 = LangChainRAGService(settings, test_dir)
    output = f.getvalue()
    print(output)
    assert "1 clean chunks, 1 new chunks" in output
    print("✓ Modified file triggered re-indexing of only that file")

    print("\n--- Fourth Run (Add new file, delete old) ---")
    file2.unlink()
    file3 = test_dir / "test3.md"
    file3.write_text("# Test 3\nNew file content", encoding="utf-8")
    
    f = StringIO()
    with contextlib.redirect_stdout(f):
        rag4 = LangChainRAGService(settings, test_dir)
    output = f.getvalue()
    print(output)
    # test1 is clean, test3 is new. test2 was deleted.
    assert "1 clean chunks, 1 new chunks" in output
    sources = [c.metadata["source"] for c in rag4._chunks]
    print(f"Final sources in chunks: {set(sources)}")
    assert "test1.md" in sources
    assert "test2.md" not in sources
    assert "test3.md" in sources
    print("✓ Correctly handled addition and deletion")

    # Cleanup
    shutil.rmtree(test_dir)
    shutil.rmtree(settings.chroma_path)

if __name__ == "__main__":
    from unittest.mock import MagicMock
    try:
        test_incremental_rag()
        print("\nIncremental RAG Verification PASSED!")
    except Exception as e:
        print(f"\nVerification FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
