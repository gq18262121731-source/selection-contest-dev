import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.models.user_model import UserRole
from agent.langgraph_health_agent import HealthAgentService, AgentState

def test_rag_trigger():
    # Mock settings
    settings = MagicMock()
    settings.rag_top_k = 3
    settings.qwen_enable_rerank = False
    settings.local_default_model = "qwen2.5-7b-instruct"
    settings.preferred_llm_provider = "ollama"
    
    # Mock services
    rag_service = MagicMock()
    rag_service.search.return_value = ["Local knowledge about high blood pressure."]
    
    analysis_service = MagicMock()
    context_assembler = MagicMock()
    tool_adapter = MagicMock()
    model_suite = MagicMock()
    
    # Initialize service
    service = HealthAgentService(
        settings,
        rag_service,
        analysis_service,
        context_assembler=context_assembler,
        tool_adapter=tool_adapter,
        model_suite=model_suite
    )
    
    # Test _should_search
    health_q = "高血压老人早餐吃什么好？"
    non_health_q = "今天天气怎么样？"
    
    print(f"Testing _should_search for: {health_q}")
    assert service._should_search(question=health_q, workflow="free_chat") == True
    print("✓ Health question triggers search")
    
    print(f"Testing _should_search for: {non_health_q}")
    assert service._should_search(question=non_health_q, workflow="free_chat") == True # Weather is also a keyword
    print("✓ Weather question triggers search")

    # Test _build_tool_calls for elder role (device scope)
    state = {
        "role": UserRole.ELDER,
        "scope": "device",
        "question": health_q,
        "workflow": "free_chat",
        "target_device_mac": "AA:BB:CC:DD:EE:FF"
    }
    
    calls = service._build_tool_calls(state)
    call_names = [c.name for c in calls]
    print(f"Tool calls for elder query: {call_names}")
    assert "run_tavily_search" in call_names
    print("✓ run_tavily_search included in elder device scope")

    # Test _prompt_node extraction
    tool_results = [
        {
            "name": "run_tavily_search",
            "success": True,
            "data": {
                "results": [
                    {"title": "Health Advice", "snippet": "Oatmeal is good for hypertension."}
                ]
            }
        }
    ]
    
    state.update({
        "knowledge_hits": ["Local: Avoid salt."],
        "tool_results": tool_results,
        "context_bundle": {},
        "analysis_payload": {}
    })
    
    # Mock build_prompt_package to see what's passed
    with patch('agent.langgraph_health_agent.build_prompt_package') as mock_build:
        mock_build.return_value = {"system": "sys", "user": "usr"}
        service._prompt_node(state)
        
        args, kwargs = mock_build.call_args
        print(f"Prompt Package kwargs: {kwargs.keys()}")
        assert "search_context" in kwargs
        assert "Oatmeal" in kwargs["search_context"]
        print("✓ search_context correctly extracted and passed to builder")

if __name__ == "__main__":
    try:
        test_rag_trigger()
        print("\nAll RAG verification tests PASSED!")
    except Exception as e:
        print(f"\nVerification FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
