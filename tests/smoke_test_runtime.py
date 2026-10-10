import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.intent_engine import IntentEngine
from core.tool_registry import tool_registry
from core.content_generator import ContentGenerator
from core.os.browser_manager import BrowserManager
from core.multi_step_planner import MultiStepPlanner

def run_smoke():
    ie = IntentEngine()
    cg = ContentGenerator()
    bm = BrowserManager()
    planner = MultiStepPlanner(intent_engine=ie)

    print("=== 1. Tool Registry Capabilities ===")
    print(tool_registry.get_capabilities_summary())

    print("\n=== 2. Browser Status ===")
    print(bm.get_browser_status())

    print("\n=== 3. Content Drafting & Verification ===")
    draft = cg.draft_content("Project Milestone Completion", content_type="email")
    print(f"Content Type: {draft['content_type']}")
    print(f"Spoken Voice: {draft['spoken_text']}")
    print(f"Content Source: {draft['source']}")
    print("Draft Preview:")
    print(draft['content'])

    file_res = cg.create_and_save_file("logs/smoke_test_doc.md", draft['content'])
    print(f"\nFile Creation: Success={file_res['success']}, Path={file_res.get('path')}, Bytes={file_res.get('size_bytes')}")

    print("\n=== 4. Natural Command Routing ===")
    test_cases = [
        "What can you do",
        "Open Chrome",
        "Search the web for the latest AI news",
        "Search YouTube for Python tutorials",
        "Search GitHub for this repository",
        "Open YouTube and search for React tutorials",
        "Write a professional email about project delay",
        "Create a folder for my college notes",
        "Find the PDF I downloaded yesterday",
        "Explain this Python error: ZeroDivisionError",
        "Close tab",
        "Pause video",
        "Run the tests"
    ]
    for c in test_cases:
        node = ie.parse(c)
        intent = node.get("intent")
        action = node.get("action")
        prov = node.get("provider")
        target = node.get("target")
        print(f"'{c}' -> Intent={intent}, Action={action}, Provider={prov}, Target={target}")

    print("\n=== 5. Multi-Step Execution Plan ===")
    compound_prompts = [
        "Open Chrome, go to YouTube, and search for Python tutorials",
        "Open YouTube and search for React tutorials",
        "Create a folder for college notes, write a readme, and save a readme to college notes"
    ]
    for prompt in compound_prompts:
        plan = planner.plan(prompt)
        print(f"\nPrompt: '{prompt}' ({len(plan)} steps)")
        for s in plan:
            print(f"  Step {s['step_index']}: '{s['clean_text']}' -> Intent={s['intent_node']['intent']}")

    print("\nSMOKE TEST COMPLETED SUCCESSFULLY!")

if __name__ == "__main__":
    run_smoke()
